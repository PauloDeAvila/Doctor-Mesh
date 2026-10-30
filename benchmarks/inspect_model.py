"""Headless benchmark loader and inspector for indexed test models."""
import os
import sys
import json
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.config import InspectionConfig


def run_inspection(model_path=None, output_report_path=None):
    if model_path is None:
        model_path = ROOT / "benchmarks" / "models" / "mech_torso.fbx"
    else:
        model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found at: {model_path}")

    # Clear current scene
    bpy.ops.wm.read_factory_settings(use_empty=True)

    print(f"Loading model into Blender: {model_path}")
    # Import FBX
    bpy.ops.import_scene.fbx(filepath=str(model_path))

    objects = list(bpy.context.scene.objects)
    mesh_objects = [o for o in objects if o.type == "MESH"]
    print(f"Loaded {len(objects)} total objects ({len(mesh_objects)} mesh objects).")

    # Configure scanner with frozen InspectionConfig
    config = InspectionConfig(max_vertices=2_000_000, max_seconds=600.0)

    scanner = ProjectScanner(bpy.context, selected=False, config=config)
    report = scanner.run()

    summary = report.get("summary", {})
    print("\n=================== SCAN SUMMARY ===================")
    print(f"Total Objects Scanned: {summary.get('objects')}")
    print(f"Mesh Objects Scanned: {summary.get('mesh_objects')}")
    print(f"Base Findings (Defects): {summary.get('base_findings')}")
    print(f"Errors: {summary.get('errors')}")
    print(f"Elapsed Time: {summary.get('elapsed_seconds', 0):.2f}s")

    # Aggregate defect statistics across meshes
    finding_counts = {}
    total_vertices = 0
    total_faces = 0
    clean_meshes = 0
    defective_meshes = 0

    for obj in report.get("objects", []):
        base = obj.get("base", {})
        total_vertices += base.get("vertices", 0)
        total_faces += base.get("faces", 0)
        findings = base.get("findings", [])
        if findings:
            defective_meshes += 1
            for finding in findings:
                ftype = finding.get("type", "unknown")
                finding_counts[ftype] = finding_counts.get(ftype, 0) + finding.get("count", 1)
        else:
            clean_meshes += 1

    print(f"Total Geometry Count: {total_vertices:,} vertices | {total_faces:,} faces")
    print(f"Mesh Health: {clean_meshes} clean meshes | {defective_meshes} meshes with findings")
    print("\nDefects identified by category:")
    for ftype, count in sorted(finding_counts.items(), key=lambda x: -x[1]):
        print(f"  - {ftype}: {count} occurrences")
    print("====================================================")

    if output_report_path is None:
        output_report_path = ROOT / "reports" / "mech_torso_initial_scan.json"
    else:
        output_report_path = Path(output_report_path)

    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nFull scan report saved to: {output_report_path}")
    return report


if __name__ == "__main__":
    run_inspection()
