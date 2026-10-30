"""Full automated repair pipeline for the indexed Mech Torso model.

Performs deterministic topological sanitation, radial/bowtie non-manifold removal,
and outward normal alignment across all 103 mesh objects, producing validated .blend and .fbx files.
"""
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
import bmesh
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.config import InspectionConfig
from ai_mesh_doctor.geometry import analyze_mesh


def repair_single_mesh(obj):
    """Deterministically repair topological anomalies on a single mesh object."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    # 1. Dissolve degenerate zero-length edges
    try:
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=list(bm.edges))
    except Exception:
        pass

    # 2. Detect and remove zero-area/redundant internal faces causing radial non-manifold edges (> 2 faces sharing an edge)
    radial_edges = [e for e in bm.edges if len(e.link_faces) > 2]
    if radial_edges:
        faces_to_remove = set()
        for e in radial_edges:
            for f in e.link_faces:
                if f.calc_area() < 1e-5:
                    faces_to_remove.add(f)
        if faces_to_remove:
            bmesh.ops.delete(bm, geom=list(faces_to_remove), context="FACES")

    # 3. Resolve bowtie / pinch non-manifold vertices (separate distinct surface fans)
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

    # 4. Remove orphan edges (edges with no link faces) and isolated vertices
    orphan_edges = [e for e in bm.edges if not e.link_faces]
    if orphan_edges:
        bmesh.ops.delete(bm, geom=orphan_edges, context="EDGES")

    loose_v = [v for v in bm.verts if not v.link_edges]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")

    # 5. Recalculate face normals for consistent orientation
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return True


def run_full_pipeline():
    input_model = ROOT / "benchmarks" / "models" / "mech_torso.fbx"
    output_blend = ROOT / "benchmarks" / "models" / "mech_torso_repaired.blend"
    output_fbx = ROOT / "benchmarks" / "models" / "mech_torso_repaired.fbx"
    report_json = ROOT / "reports" / "mech_torso_repaired_comparison.json"

    print("=========================================================")
    print("      DOCTOR MESH — AUTOMATED REPAIR PIPELINE            ")
    print("=========================================================")
    print(f"Loading input model: {input_model}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(input_model))

    objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    print(f"Total mesh objects loaded: {len(objects)}")

    config = InspectionConfig(max_vertices=2_000_000, max_seconds=300.0)

    # 1. Initial Scan
    print("\n[Stage 1/4] Running pre-repair baseline scan...")
    t0 = time.monotonic()
    scanner_pre = ProjectScanner(bpy.context, selected=False, config=config)
    report_pre = scanner_pre.run()
    elapsed_pre = time.monotonic() - t0
    print(f"Pre-repair scan completed in {elapsed_pre:.2f}s")

    # 2. Repair All Meshes
    print("\n[Stage 2/4] Executing topological repair & normal alignment...")
    t1 = time.monotonic()
    for idx, obj in enumerate(objects):
        repair_single_mesh(obj)
        if (idx + 1) % 25 == 0 or (idx + 1) == len(objects):
            print(f"  Processed {idx + 1}/{len(objects)} meshes...")
    elapsed_rep = time.monotonic() - t1
    print(f"Repair pass completed in {elapsed_rep:.2f}s")

    # 3. Post-Repair Validation Scan
    print("\n[Stage 3/4] Running post-repair validation scan...")
    t2 = time.monotonic()
    scanner_post = ProjectScanner(bpy.context, selected=False, config=config)
    report_post = scanner_post.run()
    elapsed_post = time.monotonic() - t2
    print(f"Post-repair scan completed in {elapsed_post:.2f}s")

    # 4. Generate Comparative Metrics
    pre_findings = {}
    post_findings = {}

    for obj in report_pre.get("objects", []):
        for f in obj.get("base", {}).get("findings", []):
            k = f.get("type", "unknown")
            pre_findings[k] = pre_findings.get(k, 0) + f.get("count", 1)

    for obj in report_post.get("objects", []):
        for f in obj.get("base", {}).get("findings", []):
            k = f.get("type", "unknown")
            post_findings[k] = post_findings.get(k, 0) + f.get("count", 1)

    print("\n================== COMPARISON METRICS ==================")
    print(f"{'Defect Type':<32} | {'Before':>8} | {'After':>8} | {'Status'}")
    print("-" * 62)
    all_keys = sorted(set(list(pre_findings.keys()) + list(post_findings.keys())))
    for k in all_keys:
        b_cnt = pre_findings.get(k, 0)
        a_cnt = post_findings.get(k, 0)
        status = "RESOLVED" if b_cnt > 0 and a_cnt == 0 else ("REDUCED" if a_cnt < b_cnt else "UNCHANGED")
        print(f"{k:<32} | {b_cnt:>8} | {a_cnt:>8} | {status}")
    print("========================================================")

    # 5. Export Assets
    print(f"\n[Stage 4/4] Exporting repaired files...")
    # Save .blend file
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print(f"  Saved Blender Scene: {output_blend}")

    # Export .fbx file
    bpy.ops.export_scene.fbx(filepath=str(output_fbx), use_selection=False)
    print(f"  Exported Clean FBX:  {output_fbx}")

    # Save Comparison Report
    comparison_summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_model": str(input_model),
        "output_blend": str(output_blend),
        "output_fbx": str(output_fbx),
        "objects_count": len(objects),
        "metrics": {
            "before": pre_findings,
            "after": post_findings,
        },
        "timings": {
            "pre_scan_s": round(elapsed_pre, 2),
            "repair_s": round(elapsed_rep, 2),
            "post_scan_s": round(elapsed_post, 2),
        }
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(comparison_summary, f, indent=2)
    print(f"  Saved JSON Report:   {report_json}")

    print("\nPipeline finished successfully!")


if __name__ == "__main__":
    run_full_pipeline()
