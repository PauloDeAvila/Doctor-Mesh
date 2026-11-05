import bpy
import bmesh
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
# Load original
bpy.ops.import_scene.fbx(filepath=str(ROOT / "benchmarks" / "models" / "mech_torso.fbx"))

# Let's inspect objects around the chest/torso
for o in bpy.context.scene.objects:
    if o.type == 'MESH':
        # Let's look for objects with dimensions around 0.15 to 0.45
        d = o.dimensions
        loc = o.location
        if 0.15 < d.y < 0.5 and 0.15 < d.z < 0.5:
            print(f"Candidate: {o.name}, loc=({loc.x:.2f}, {loc.y:.2f}, {loc.z:.2f}), dims=({d.x:.2f}, {d.y:.2f}, {d.z:.2f}), verts={len(o.data.vertices)}")

