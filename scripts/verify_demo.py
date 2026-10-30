import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import bpy
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.reporting import atomic_json

assert len([o for o in bpy.context.scene.objects if o.type == "LIGHT"]) == 3
assert bpy.context.scene.render.engine == "octane"
assert bpy.context.scene.view_settings.view_transform == "Filmic"
assert bpy.context.scene.render.resolution_x == 3840
report = ProjectScanner(bpy.context).run()
records = {o["name"]: o for o in report["objects"]}
housing = records["CASE_C | Closed annular mechanical housing"]["base"]
assert housing["boundary_edge_count"] == 0
assert housing["radial_edge_count"] == 0
assert housing["island_count"] == 1
assert records["CASE_B | Missing face - intent needs review"]["base"]["boundary_edge_count"] == 4
assert records["CASE_A | Deliberately reversed face"]["base"]["winding_edge_count"] == 4
assert report["status"] == "complete"
atomic_json(root/"demo-reopen-results.json", {"success": True, "source": bpy.data.filepath,
    "scene_objects": len(bpy.context.scene.objects), "housing_closed": True,
    "defect_fixtures_detected": True, "preset_preserved": True, "errors": report["errors"]})
print("DEMO_REOPEN_PASS")
