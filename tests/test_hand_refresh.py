"""Exercise the real cached 0/3 update in a disposable reopened process."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from ai_mesh_doctor.identity import measurement_fingerprint
P=ROOT.parent/'mecha_small_parts_v1/black_steel_lookdev/hand_parts_0_3'
bpy.ops.wm.open_mainfile(filepath=str(P.parent/'Mecha_Side_Red_Eyes_Laser.blend'),load_ui=False,use_scripts=False)
targets=set()
for n in (0,3):
    obj=bpy.data.objects[f'tripo_part_{n}'];targets.update([obj]+list(obj.children_recursive))
before={obj.name:(measurement_fingerprint(obj.data),tuple(x for row in obj.matrix_world for x in row)) for obj in bpy.data.objects if obj.type=='MESH' and obj not in targets}
started=time.perf_counter();p=P/'refresh_installed.py'
exec(compile(p.read_text(),str(p),'exec'),{'__file__':str(p),'TEST_MODE':True})
elapsed=time.perf_counter()-started
for name,state in before.items():
    obj=bpy.data.objects[name];assert state==(measurement_fingerprint(obj.data),tuple(x for row in obj.matrix_world for x in row)),name
assert not any(obj.get('mesh_doctor_batch') for obj in bpy.data.objects)
(ROOT/'hand-refresh-test-results.json').write_text(json.dumps({'success':True,'seconds':elapsed,'unrelated_meshes_preserved':len(before),'saved':False,'source':'separate process; main live model untouched'},indent=2))
print('HAND_REFRESH_PASS',elapsed)
