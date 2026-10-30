"""Exercise real registered operators through plan > preview > apply > rollback."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import bmesh
from ai_mesh_doctor import register, unregister
from ai_mesh_doctor import ui
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.identity import mesh_fingerprint
from ai_mesh_doctor.reporting import atomic_json

ROOT = Path(__file__).resolve().parents[1]
os.environ["MESH_DOCTOR_DATA_DIR"] = str(ROOT/"tests/runtime/knowledge")
register()
obj = bpy.data.objects["Cube"]
bpy.context.view_layer.objects.active = obj
bm = bmesh.new()
bm.from_mesh(obj.data)
bm.faces.ensure_lookup_table()
bm.faces[0].normal_flip()
bm.to_mesh(obj.data)
bm.free()
original = mesh_fingerprint(obj.data)
ui._last_report = ProjectScanner(bpy.context).run()
settings = bpy.context.scene.mesh_doctor
settings.output_directory = str(ROOT/"examples/ui")
settings.whole_component = True
assert bpy.ops.mesh_doctor.plan() == {"FINISHED"}
assert bpy.ops.mesh_doctor.preview() == {"FINISHED"}
assert obj.hide_get()
assert mesh_fingerprint(obj.data) == original
settings.component_approval = True
assert bpy.ops.mesh_doctor.apply() == {"FINISHED"}
assert not obj.hide_get()
assert mesh_fingerprint(obj.data) != original
assert bpy.ops.mesh_doctor.rollback() == {"FINISHED"}
assert mesh_fingerprint(obj.data) == original
unregister()
atomic_json(ROOT/"ui-test-results.json", {"success": True, "steps": ["register", "plan", "preview", "apply", "rollback", "unregister"],
            "original_restored": True, "native_panel_visual_review": "pending"})
print("UI_OPERATOR_WORKFLOW_PASS")
