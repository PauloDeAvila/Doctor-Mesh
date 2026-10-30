import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import bpy
from ai_mesh_doctor.capture import CaptureSession,CaptureConfig
from ai_mesh_doctor.reporting import atomic_json
parent=bpy.data.objects.new('Assembly',None)
bpy.context.scene.collection.objects.link(parent)
cube=bpy.data.objects['Cube']
cube.parent=parent
second=cube.copy()
second.data=cube.data.copy()
bpy.context.scene.collection.objects.link(second)
second.parent=parent
second.location.x=3
bpy.context.view_layer.update()
before=(len(bpy.data.objects),len(bpy.data.meshes),bpy.context.scene.render.engine)
session=CaptureSession(bpy.context,parent,root/'tests/runtime/assembly-capture',CaptureConfig(width=160,height=90),scope_objects=[cube,second])
assert len(session.targets)==2
assert abs(session.center.x-1.5)<1e-6
session.jobs=session.jobs[:2]
try:
    while session.step():pass
    session.finish()
except Exception:
    session.finish(cancelled=True)
    raise
assert before==(len(bpy.data.objects),len(bpy.data.meshes),bpy.context.scene.render.engine)
atomic_json(root/'assembly-capture-test-results.json',{'success':True,'assembly_meshes':2,'source_preserved':True})
print('ASSEMBLY_CAPTURE_PASS')
