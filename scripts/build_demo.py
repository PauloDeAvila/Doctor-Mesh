"""Create an independent diagnostic .blend from the user's White Lab template."""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import bmesh
from mathutils import Matrix
from ai_mesh_doctor.reconstruction import build_component
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.reporting import atomic_json
from ai_mesh_doctor import register

ROOT = Path(__file__).resolve().parents[1]
template = ROOT.parent/"white_lab_template.blend"
bpy.ops.wm.open_mainfile(filepath=str(template))
scene = bpy.context.scene
assert scene.render.resolution_x == 3840 and scene.render.resolution_y == 2160
assert scene.view_settings.view_transform == "Filmic"
assert len([o for o in scene.objects if o.type == "LIGHT"]) == 3
assert scene.camera and not scene.camera.data.dof.use_dof
assert scene.render.engine == "octane", "Load the user's installed Octane add-on before building the demo"
kernel = scene.octane.kernel_node_graph_property.node_tree
node = next(n for n in kernel.nodes if n.bl_idname == "OctanePathTracingKernel")
assert node.inputs["Max. samples"].default_value == 512
fixtures = bpy.data.collections.new("Mesh Doctor | Demonstration Cases")
scene.collection.children.link(fixtures)


def cube(name, center):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.1)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    fixtures.objects.link(obj)
    obj.location = center
    return obj


reversed_cube = cube("CASE_A | Deliberately reversed face", (-1.7, 0, 0))
bm = bmesh.new()
bm.from_mesh(reversed_cube.data)
bm.faces.ensure_lookup_table()
bm.faces[0].normal_flip()
bm.to_mesh(reversed_cube.data)
bm.free()
open_cube = cube("CASE_B | Missing face - intent needs review", (0,0,0))
bm = bmesh.new()
bm.from_mesh(open_cube.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY")
bm.to_mesh(open_cube.data)
bm.free()
frame = Matrix.Translation((1.7,0,0))
spec = {"family": "revolved_profile", "profile": [[0.35,-0.45],[0.55,-0.45],[0.55,0.45],[0.35,0.45]],
        "depth": 0.9, "segments": 96, "frame": [list(row) for row in frame],
        "units": "world_blender_units", "measurement_evidence": ["Synthetic measured dimensions: outerD1.10 / innerD0.70 / length0.90"],
        "expected_bounds_local": [[-0.55,0.55],[-0.55,0.55],[-0.45,0.45]], "tolerance": 1e-5,
        "intentional_voids": ["Through bore diameter0.70; continuous inner wall"],
        "attachment_points": [[0.55,0,0]], "neighbor_constraints": {}}
housing, validation = build_component(spec, "CASE_C | Closed annular mechanical housing")
fixtures.objects.link(housing)
housing["mesh_doctor_specification"] = json.dumps(spec)
housing["case_status"] = "Synthetic topology/dimension test; aesthetic approval pending"
text = bpy.data.texts.new("START_HERE.md")
text.write("AI Mesh Doctor engineering test project\n\nA: one reversed cube face. B: missing face requiring design context. C: analytically closed annular housing with intentional through bore.\n\nUse N > AI Mesh Doctor. Scan Selected/Entire Project, inspect JSON, make an explicit plan, preview, validate, approve, apply or rollback. No automatic arbitrary hole fill. Source files and tests: " + str(ROOT))
try:
    register()
except ValueError:
    pass
scene.mesh_doctor.output_directory = str(ROOT/"reports")
scene.mesh_doctor.reconstruction_spec = str(ROOT/"examples/housing-specification.json")
scene.mesh_doctor.status = "Demo ready; no repair applied"
for obj in scene.objects:
    obj.select_set(False)
reversed_cube.select_set(True)
bpy.context.view_layer.objects.active = reversed_cube
bpy.context.view_layer.update()
output = ROOT/"project/AI_Mesh_Doctor_Demo.blend"
output.parent.mkdir(parents=True, exist_ok=True)
prior = bpy.context.preferences.filepaths.save_version
try:
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
finally:
    bpy.context.preferences.filepaths.save_version = prior
atomic_json(ROOT/"examples/housing-specification.json", spec)
atomic_json(ROOT/"examples/demo-housing-validation.json", validation)
atomic_json(ROOT/"reports/demo-inspection.json", ProjectScanner(bpy.context).run())
atomic_json(ROOT/"demo-build-results.json", {"success": True, "file": str(output), "engine": scene.render.engine,
    "resolution": [scene.render.resolution_x,scene.render.resolution_y], "samples": node.inputs["Max. samples"].default_value,
    "filmic": scene.view_settings.view_transform, "lights": 3, "new_functional_parts": 3, "render_started": False})
print("DEMO_BUILD_PASS", output)
