"""blender --background file.blend --python scan_project.py -- --output report.json"""
import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.config import InspectionConfig
from ai_mesh_doctor.reporting import atomic_json

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--max-vertices", type=int, default=250000)
parser.add_argument("--max-seconds", type=float, default=120)
parser.add_argument("--base-only", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
report = ProjectScanner(bpy.context, config=InspectionConfig(max_vertices=args.max_vertices,
                        max_seconds=args.max_seconds, inspect_evaluated=not args.base_only)).run()
atomic_json(args.output, report)
print("MESH_DOCTOR_REPORT", args.output, report["status"], report["summary"])
