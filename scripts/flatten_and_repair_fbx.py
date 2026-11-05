"""
Doctor Mesh — Local Per-Vertex Planarity Correction v6.0

Architecture change: removed global facet segmentation entirely.

Instead of growing facets and fitting global planes (which creates seam artifacts
at facet boundaries), each vertex independently checks its local 2-hop neighborhood:
  - If the neighborhood is flat (low normal variance) → this vertex is on a plate
  - If the vertex is an outlier (significantly off the local plane) → project it
  - Otherwise leave it untouched

Benefits:
  - No global seam artifacts between competing plane regions
  - Scale-adaptive thresholds via median edge length
  - Feature-protected: bolt/rivet regions are excluded before any correction
  - Simpler, more predictable, easier to tune
"""
import sys
import time
import math
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
import bmesh
from mathutils import Vector


# ---------------------------------------------------------------------------
# TUNING CONSTANTS
# ---------------------------------------------------------------------------
SHARP_DEG              = 22.0
CREASE_RAD             = math.radians(SHARP_DEG)

# Feature detection
CURVATURE_THRESHOLD    = 0.10       # Normal variance per vertex → bolt/rivet/groove
PROTECTION_HOPS        = 2          # Exclusion zone around features

# Local planarity check
LOCAL_FLAT_VAR         = 0.04       # Max normal variance to consider a 2-hop region flat
                                     # 0.04 ≈ allows ±11° spread across local neighborhood

# Outlier correction
OUTLIER_EDGE_FACTOR    = 3.0        # Correct vertex only if |dist| > FACTOR × median_edge
                                     # Keeps micro-detail intact, only fixes real dents

# Taubin — very light final pass only
TAUBIN_LAMBDA          = 0.45
TAUBIN_MU              = -0.48
TAUBIN_ITERS           = 3


# ---------------------------------------------------------------------------
# STEP 1 — Topological Cleanup
# ---------------------------------------------------------------------------
def cleanup_topology(bm):
    try:
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=list(bm.edges))
    except Exception:
        pass

    radial = [e for e in bm.edges if len(e.link_faces) > 2]
    if radial:
        to_del = {f for e in radial for f in e.link_faces if f.calc_area() < 1e-5}
        if to_del:
            bmesh.ops.delete(bm, geom=list(to_del), context="FACES")

    bm.verts.ensure_lookup_table()
    nm_verts = [v for v in bm.verts if not v.is_manifold]
    for v in nm_verts:
        faces = list(v.link_faces)
        if len(faces) <= 1:
            continue
        fans, visited = [], set()
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

    orphan_edges = [e for e in bm.edges if not e.link_faces]
    if orphan_edges:
        bmesh.ops.delete(bm, geom=orphan_edges, context="EDGES")
    loose_v = [v for v in bm.verts if not v.link_edges]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))


# ---------------------------------------------------------------------------
# STEP 2 — Feature Detection & Exclusion Mask
# ---------------------------------------------------------------------------
def compute_feature_exclusion_mask(bm):
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()

    feature_verts = set()

    # Sharp edges & boundary
    for e in bm.edges:
        is_sharp = e.is_boundary or (e.is_manifold and e.calc_face_angle(0) > CREASE_RAD)
        if is_sharp:
            for v in e.verts:
                feature_verts.add(v.index)

    # High local curvature (bolts, rivets, concentric features)
    for v in bm.verts:
        lf = v.link_faces
        if len(lf) < 3:
            feature_verts.add(v.index)
            continue
        normals = np.array([list(f.normal) for f in lf], dtype=float)
        if normals.var(axis=0).sum() > CURVATURE_THRESHOLD:
            feature_verts.add(v.index)

    # Flood-fill protection zone
    adj = defaultdict(set)
    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        adj[a].add(b)
        adj[b].add(a)

    protected = set(feature_verts)
    frontier = set(feature_verts)
    for _ in range(PROTECTION_HOPS):
        next_frontier = set()
        for vi in frontier:
            for ni in adj[vi]:
                if ni not in protected:
                    protected.add(ni)
                    next_frontier.add(ni)
        frontier = next_frontier
        if not frontier:
            break

    return protected


# ---------------------------------------------------------------------------
# STEP 3 — Local Per-Vertex Planarity Correction (core of v6)
# ---------------------------------------------------------------------------
def correct_outlier_vertices(bm, protected_verts, median_edge):
    """
    For each non-protected vertex:
    1. Collect its 2-hop face neighborhood (directly linked faces + their face neighbors)
    2. Check if the neighborhood is locally flat (normal variance < LOCAL_FLAT_VAR)
    3. If flat: compute area-weighted average normal and center of local faces
    4. If vertex is significantly off that plane → project it

    No global regions, no seam artifacts.
    """
    bm.verts.ensure_lookup_table()
    bm.normal_update()

    min_outlier_dist = OUTLIER_EDGE_FACTOR * median_edge
    corrected = 0

    for v in bm.verts:
        if v.index in protected_verts:
            continue
        if not v.link_faces:
            continue

        # 2-hop face neighborhood: own faces + edge-adjacent faces of those faces
        local_faces = set(v.link_faces)
        for f0 in list(v.link_faces):
            for e in f0.edges:
                for f1 in e.link_faces:
                    local_faces.add(f1)

        if len(local_faces) < 4:
            continue

        # Planarity gate: skip if local region is curved/complex
        normals = np.array([list(f.normal) for f in local_faces], dtype=float)
        if normals.var(axis=0).sum() > LOCAL_FLAT_VAR:
            continue  # Curved or feature region — preserve as-is

        # Area-weighted average normal and center of the local plane
        total_area = sum(f.calc_area() for f in local_faces)
        if total_area < 1e-12:
            continue

        avg_normal = Vector((0.0, 0.0, 0.0))
        center = Vector((0.0, 0.0, 0.0))
        for f in local_faces:
            w = f.calc_area() / total_area
            avg_normal += f.normal * w
            center += f.calc_center_median() * w

        if avg_normal.length < 1e-6:
            continue
        avg_normal.normalize()

        # Signed distance from vertex to local plane
        dist = (v.co - center).dot(avg_normal)

        # Only correct if the vertex is a genuine outlier (real dent, not micro-detail)
        if abs(dist) > min_outlier_dist:
            v.co -= avg_normal * dist
            corrected += 1

    return corrected


# ---------------------------------------------------------------------------
# STEP 4 — Light Taubin to smooth correction transitions
# ---------------------------------------------------------------------------
def micro_taubin(bm, protected_verts):
    bm.verts.ensure_lookup_table()
    movable = [v for v in bm.verts
               if v.index not in protected_verts and v.link_edges and not v.is_boundary]

    for _ in range(TAUBIN_ITERS):
        d_pos = {}
        for v in movable:
            neighbors = [e.other_vert(v) for e in v.link_edges]
            if not neighbors:
                continue
            avg = sum((n.co for n in neighbors), Vector()) / len(neighbors)
            d_pos[v] = (avg - v.co) * TAUBIN_LAMBDA
        for v, d in d_pos.items():
            v.co += d

        d_neg = {}
        for v in movable:
            neighbors = [e.other_vert(v) for e in v.link_edges]
            if not neighbors:
                continue
            avg = sum((n.co for n in neighbors), Vector()) / len(neighbors)
            d_neg[v] = (avg - v.co) * TAUBIN_MU
        for v, d in d_neg.items():
            v.co += d


# ---------------------------------------------------------------------------
# Main per-object pipeline
# ---------------------------------------------------------------------------
def process_mesh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    cleanup_topology(bm)
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Compute scale-adaptive threshold
    lengths = [e.calc_length() for e in bm.edges if e.calc_length() > 0]
    if lengths:
        lengths.sort()
        median_edge = lengths[len(lengths) // 2]
    else:
        median_edge = 0.01

    protected_verts = compute_feature_exclusion_mask(bm)
    corrected = correct_outlier_vertices(bm, protected_verts, median_edge)
    micro_taubin(bm, protected_verts)

    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    mod = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    mod.mode = 'FACE_AREA'
    mod.weight = 100
    mod.keep_sharp = True
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=mod.name)

    return corrected, median_edge


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------
def run_pipeline():
    input_model = ROOT / "benchmarks" / "models" / "mech_torso.fbx"
    output_fbx  = ROOT / "benchmarks" / "models" / "mech_torso_repaired.fbx"
    report_json = ROOT / "reports" / "mech_torso_repaired_comparison.json"

    print("=" * 65)
    print("  DOCTOR MESH v6.0 — Local Per-Vertex Planarity Correction")
    print("=" * 65)
    print(f"Input : {input_model}")
    print(f"Output: {output_fbx}")
    print(f"Config: sharp={SHARP_DEG}deg | hops={PROTECTION_HOPS}"
          f" | flat_var<{LOCAL_FLAT_VAR}"
          f" | outlier>{OUTLIER_EDGE_FACTOR}x_median_edge"
          f" | taubin_iters={TAUBIN_ITERS}")
    print()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(input_model))

    objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    print(f"Loaded {len(objects)} mesh objects.")

    total_corrected = 0
    median_edges = []
    t0 = time.monotonic()

    for idx, obj in enumerate(objects):
        cnt, med = process_mesh(obj)
        total_corrected += cnt
        median_edges.append(med)
        if (idx + 1) % 20 == 0 or (idx + 1) == len(objects):
            elapsed = time.monotonic() - t0
            print(f"  [{idx+1:3d}/{len(objects)}] done"
                  f" | corrected={total_corrected}"
                  f" | med_edge={med:.4f}"
                  f" | {elapsed:.1f}s")

    elapsed = time.monotonic() - t0
    avg_med = sum(median_edges) / len(median_edges) if median_edges else 0
    print(f"\nPipeline completed in {elapsed:.2f}s")
    print(f"Total outlier vertices corrected: {total_corrected}")
    print(f"Avg median edge length: {avg_med:.5f} units"
          f" → outlier threshold = {OUTLIER_EDGE_FACTOR * avg_med:.5f} units")

    print(f"\nExporting FBX → {output_fbx}")
    output_fbx.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=str(output_fbx), use_selection=False)
    print("Export complete.")

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "6.0",
        "algorithm": "local-per-vertex-planarity",
        "config": {
            "sharp_deg": SHARP_DEG,
            "curvature_threshold": CURVATURE_THRESHOLD,
            "protection_hops": PROTECTION_HOPS,
            "local_flat_var": LOCAL_FLAT_VAR,
            "outlier_edge_factor": OUTLIER_EDGE_FACTOR,
            "taubin_iters": TAUBIN_ITERS,
            "avg_median_edge": round(avg_med, 6),
            "outlier_threshold_units": round(OUTLIER_EDGE_FACTOR * avg_med, 6),
        },
        "input_model": str(input_model),
        "output_fbx": str(output_fbx),
        "objects_count": len(objects),
        "total_outlier_verts_corrected": total_corrected,
        "elapsed_seconds": round(elapsed, 2),
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Report → {report_json}")


if __name__ == "__main__":
    run_pipeline()
