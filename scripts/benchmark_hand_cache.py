"""Read-only benchmark on the saved 0/3 assemblies, in a separate Blender."""
import sys,time,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.config import InspectionConfig
blend=ROOT.parent/'mecha_small_parts_v1/black_steel_lookdev/Mecha_Side_Red_Eyes_Laser.blend'
bpy.ops.wm.open_mainfile(filepath=str(blend),load_ui=False,use_scripts=False)
targets=[]
for n in (0,3):
    obj=bpy.data.objects[f'tripo_part_{n}'];targets.extend([obj]+[o for o in obj.children_recursive if o.type=='MESH'])
results=[]
with tempfile.TemporaryDirectory() as directory:
    for phase in ('cold','warm'):
        started=time.perf_counter();scanner=ProjectScanner(bpy.context,selected=True,
            config=InspectionConfig(max_seconds=120,max_vertices=150000),cache_directory=directory)
        scanner.queue=targets;scanner.total=len(targets);report=scanner.run()
        if report['status']!='complete':raise RuntimeError('Incomplete benchmark inspection')
        results.append({'phase':phase,'seconds':time.perf_counter()-started,**report['summary']})
result={'scope':'saved part0/3 only, separate background process, no model saved',
        'objects':len(targets),'runs':results,'speedup':results[0]['seconds']/results[1]['seconds']}
(ROOT/'cache-benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
