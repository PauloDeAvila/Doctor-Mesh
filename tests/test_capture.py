import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from ai_mesh_doctor.capture import CaptureSession, CaptureConfig, view_schedule, cleanup_approved
from ai_mesh_doctor.reporting import atomic_json

root = Path(__file__).resolve().parents[1]
before = {"scene": bpy.context.scene.name, "engine": bpy.context.scene.render.engine,
          "camera": bpy.context.scene.camera, "objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes),
          "cameras": len(bpy.data.cameras), "resolution": bpy.context.scene.render.resolution_x}
target = bpy.data.objects.get("Cube")
assert target is not None
schedule = view_schedule()
assert len(schedule) == 62
assert len([v for v in schedule if v[0].startswith("vertical_")]) == 24
session = CaptureSession(bpy.context, target, root/"examples/captures", CaptureConfig(width=160, height=90))
try:
    while session.step():
        pass
    manifest = session.finish()
except Exception:
    session.finish(cancelled=True)
    raise
assert len(manifest["files"]) == 124
assert bpy.context.scene.name == before["scene"]
assert bpy.context.scene.render.engine == before["engine"]
assert bpy.context.scene.camera == before["camera"]
assert len(bpy.data.objects) == before["objects"]
assert len(bpy.data.meshes) == before["meshes"]
assert len(bpy.data.cameras) == before["cameras"]
assert bpy.context.scene.render.resolution_x == before["resolution"]
try:
    cleanup_approved(session.manifest_path)
except ValueError:
    pass
else:
    raise AssertionError("Cleanup without approval was accepted")
atomic_json(root/"capture-test-results.json", {"success": True, "images_rendered": 124,
            "scheduled_full_views": 124, "manifest": str(session.manifest_path), "settings_preserved": True})
print("CAPTURE_TEST_PASS", session.manifest_path)
