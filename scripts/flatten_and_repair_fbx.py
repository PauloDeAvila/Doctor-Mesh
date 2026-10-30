"""Complete hard-surface planar projection, dent removal and topological repair pipeline.
Processes all 103 objects of mech_torso and exports exclusively to clean FBX.
"""
import sys
import time
import math
import json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
import bmesh
from mathutils import Vector


def process_mesh(obj):
    """Sanitize topology, project crumpled facets to planes, and smooth out dents."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    # -------------------------------------------------------------
    # Step 1: Topological Cleanup
    # -------------------------------------------------------------
    # Dissolve zero-length edges
    try:
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=list(bm.edges))
    except Exception:
        pass

    # Remove radial degenerate internal faces
    radial = [e for e in bm.edges if len(e.link_faces) > 2]
    if radial:
        to_del = {f for e in radial for f in e.link_faces if f.calc_area() < 1e-5}
        if to_del:
            bmesh.ops.delete(bm, geom=list(to_del), context="FACES")

    # Resolve bowtie non-manifold vertices
    bm.verts.ensure_lookup_table()
    nm_verts = [v for v in bm.verts if not v.is_manifold]
    if nm_verts:
        for v in nm_verts:
            faces = list(v.link_faces)
            if len(faces) <= 1:
                continue
            fans = []
            visited = set()
            for f in faces:
                if f in visited:
                    continue
                fan = [f]
                visited.add(f)
                queue = [f]
                while queue:
                    curr = queue.pop()
                    for e in curr.edges:
                        if v in e.verts:
                            for nbr in e.link_faces:
                                if nbr in faces and nbr not in visited:
                                    visited.add(nbr)
                                    fan.append(nbr)
                                    queue.append(nbr)
                fans.append(fan)
            if len(fans) > 1:
                for fan in fans[1:]:
                    new_v = bm.verts.new(v.co)
                    for f in fan:
                        new_verts = [new_v if vert == v else vert for vert in f.verts]
                        bm.faces.new(new_verts)
                    bmesh.ops.delete(bm, geom=fan, context="FACES")

    # Clean loose vertices/orphan edges
    orphan_edges = [e for e in bm.edges if not e.link_faces]
    if orphan_edges:
        bmesh.ops.delete(bm, geom=orphan_edges, context="EDGES")
    loose_v = [v for v in bm.verts if not v.link_edges]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")

    # Recalculate face normals for consistent outward orientation
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))

    # -------------------------------------------------------------
    # Step 2: Planar Facet Segmentation & Projection
    # -------------------------------------------------------------
    sharp_rad = math.radians(24) # True mechanical creases
    sharp_edges = set()
    for e in bm.edges:
        if e.is_boundary or (e.is_manifold and e.calc_face_angle(0) > sharp_rad):
            sharp_edges.add(e)
            e.smooth = False
        else:
            e.smooth = True

    # Segment faces into contiguous normal-consistent facets
    visited_faces = set()
    sorted_faces = sorted(list(bm.faces), key=lambda f: -f.calc_area())
    facets = []

    for seed in sorted_faces:
        if seed in visited_faces:
            continue
        facet = [seed]
        visited_faces.add(seed)
        seed_normal = seed.normal.copy()
        q = [seed]
        while q:
            curr = q.pop()
            for e in curr.edges:
                if e in sharp_edges:
                    continue
                for nbr in e.link_faces:
                    if nbr not in visited_faces and nbr.normal.dot(seed_normal) > 0.88:
                        visited_faces.add(nbr)
                        facet.append(nbr)
                        q.append(nbr)
        if len(facet) >= 20: # Significant plate facet
            facets.append(facet)

    # Flatten interior vertices of planar facets
    projected_count = 0
    for facet in facets:
        facet_set = set(facet)
        facet_verts = {v for f in facet for v in f.verts}
        interior = [v for v in facet_verts if all(f in facet_set for f in v.link_faces)]
        if len(interior) < 8:
            continue

        # Fit best plane with PCA
        pts = np.array([tuple(v.co) for f in facet for v in f.verts], dtype=float)
        center = pts.mean(axis=0)
        cov = (pts - center).T @ (pts - center)
        eigvals, eigvecs = np.linalg.eigh(cov)

        ratio = eigvals[0] / (eigvals.sum() + 1e-12)
        if ratio < 0.12: # High confidence planar facet
            normal = Vector(eigvecs[:, 0]).normalized()
            origin = Vector(center)

            for v in interior:
                dist = (v.co - origin).dot(normal)
                v.co -= normal * dist
                projected_count += 1

    # -------------------------------------------------------------
    # Step 3: Adaptive Taubin Fairing for Gentle Curves/Transitions
    # -------------------------------------------------------------
    sharp_verts = {v for e in sharp_edges for v in e.verts}
    movable = [v for v in bm.verts if v not in sharp_verts and v.link_edges]

    lam = 0.45
    mu = -0.48
    for _ in range(8):
        d_pos = {}
        for v in movable:
            avg = sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges)
            d_pos[v] = (avg - v.co) * lam
        for v, d in d_pos.items():
            v.co += d

        d_neg = {}
        for v in movable:
            avg = sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges)
            d_neg[v] = (avg - v.co) * mu
        for v, d in d_neg.items():
            v.co += d

    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    # -------------------------------------------------------------
    # Step 4: Apply Weighted Normal for Crisp Shading
    # -------------------------------------------------------------
    mod = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    mod.mode = 'FACE_AREA'
    mod.weight = 100
    mod.keep_sharp = True

    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=mod.name)

    return projected_count


def run_pipeline():
    input_model = ROOT / "benchmarks" / "models" / "mech_torso.fbx"
    output_fbx = ROOT / "benchmarks" / "models" / "mech_torso_repaired.fbx"
    report_json = ROOT / "reports" / "mech_torso_repaired_comparison.json"

    print("=================================================================")
    print("      DOCTOR MESH — ADVANCED HARD-SURFACE FLATTENING PIPELINE    ")
    print("=================================================================")
    print(f"Loading input model: {input_model}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(input_model))

    objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    print(f"Total objects loaded: {len(objects)}")

    total_projected = 0
    t0 = time.monotonic()
    for idx, obj in enumerate(objects):
        cnt = process_mesh(obj)
        total_projected += cnt
        if (idx + 1) % 25 == 0 or (idx + 1) == len(objects):
            print(f"  Processed {idx + 1}/{len(objects)} meshes ({total_projected} vertices projected so far)...")

    elapsed = time.monotonic() - t0
    print(f"\nSurface flattening completed in {elapsed:.2f}s!")
    print(f"Total vertices projected directly onto planar equations: {total_projected}")

    # Export exclusively to FBX as requested
    print(f"\nExporting clean FBX to: {output_fbx}")
    output_fbx.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=str(output_fbx), use_selection=False)
    print("Export complete!")

    # Save summary report
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_model": str(input_model),
        "output_fbx": str(output_fbx),
        "objects_count": len(objects),
        "total_vertices_projected_to_planes": total_projected,
        "elapsed_seconds": round(elapsed, 2)
    }
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Report saved to: {report_json}")


if __name__ == "__main__":
    run_pipeline()
