import bpy
import bmesh
import math
from mathutils import Vector
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(ROOT / "benchmarks" / "models" / "mech_torso.fbx"))

obj = bpy.context.scene.objects.get("tripo_part_1")
bm = bmesh.new()
bm.from_mesh(obj.data)

# Find all edges with high dihedral angle
angles = [(e, math.degrees(e.calc_face_angle(0))) for e in bm.edges if e.is_manifold]
angles.sort(key=lambda x: -x[1])

print(f"Top 10 highest angle edges in tripo_part_1:")
for e, a in angles[:10]:
    print(f"  Edge {e.index}: {a:.1f} deg, length={e.calc_length():.5f}, verts={[v.index for v in e.verts]}")

# Look at curvature / variance around small circles
# Cylindrical sockets have circular loops of edges
sharp_15 = [e for e in bm.edges if e.is_boundary or (e.is_manifold and e.calc_face_angle(0) > math.radians(15))]
print(f"Edges with angle > 15 deg: {len(sharp_15)} out of {len(bm.edges)}")
sharp_20 = [e for e in bm.edges if e.is_boundary or (e.is_manifold and e.calc_face_angle(0) > math.radians(20))]
print(f"Edges with angle > 20 deg: {len(sharp_20)} out of {len(bm.edges)}")
sharp_30 = [e for e in bm.edges if e.is_boundary or (e.is_manifold and e.calc_face_angle(0) > math.radians(30))]
print(f"Edges with angle > 30 deg: {len(sharp_30)} out of {len(bm.edges)}")

bm.free()

