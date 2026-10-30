"""Synthetic integration tests; run in a separate Blender background process."""
import sys
import json
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import bmesh
from mathutils import Matrix
from ai_mesh_doctor import register, unregister
from ai_mesh_doctor.config import InspectionConfig
from ai_mesh_doctor.geometry import analyze_mesh
from ai_mesh_doctor.identity import mesh_fingerprint
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.reporting import atomic_json, validate_report
from ai_mesh_doctor.knowledge import KnowledgeStore
from ai_mesh_doctor.policy import skill_manifest

CONFIG = InspectionConfig()
ROOT = Path(__file__).resolve().parents[1]


def mesh_object(name="Fixture"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def edit(obj, function):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    function(bm)
    bm.to_mesh(obj.data)
    bm.free()


class Integration(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def inspect(self, obj):
        return analyze_mesh(obj.data, obj.matrix_world, CONFIG)

    def test_clean_manifold_untouched(self):
        obj = mesh_object()
        before = mesh_fingerprint(obj.data)
        report = self.inspect(obj)
        self.assertTrue(report["closed_topology_candidate"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(before, mesh_fingerprint(obj.data))
        self.assertAlmostEqual(report["shells"][0]["signed_volume_world"], 8)

    def test_missing_face_is_not_automatically_defect_or_cap(self):
        obj = mesh_object()
        edit(obj, lambda bm: bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY"))
        result = self.inspect(obj)
        self.assertEqual(result["boundary_edge_count"], 4)
        self.assertTrue(result["regions"][0]["closed_loop"])
        self.assertFalse(result["regions"][0]["automatic_fill_allowed"])
        self.assertEqual(len(obj.data.polygons), 5)

    def test_duplicates_and_loose_geometry(self):
        obj = mesh_object()
        edit(obj, lambda bm: bm.verts.new(bm.verts[0].co))
        result = self.inspect(obj)
        self.assertEqual(result["duplicate_pair_count"], 1)
        self.assertEqual(result["loose_vertex_count"], 1)
        self.assertEqual(result["island_count"], 2)

    def test_degenerate_polygon(self):
        mesh = bpy.data.meshes.new("Degenerate")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [], [(0, 1, 2)])
        result = analyze_mesh(mesh, Matrix.Identity(4), CONFIG)
        self.assertEqual(result["degenerate_face_count"], 1)

    def test_reversed_face(self):
        obj = mesh_object()
        edit(obj, lambda bm: bm.faces[0].normal_flip())
        self.assertEqual(self.inspect(obj)["winding_edge_count"], 4)

    def test_inverted_closed_shell(self):
        obj = mesh_object()
        edit(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=list(bm.faces)))
        self.assertLess(self.inspect(obj)["shells"][0]["signed_volume_world"], 0)

    def test_nonplanar_quad(self):
        obj = mesh_object()
        edit(obj, lambda bm: setattr(bm.verts[0].co, "z", bm.verts[0].co.z+0.3))
        self.assertGreater(self.inspect(obj)["planarity_deviation_world"]["max"], 0)

    def test_intentional_asymmetry_not_a_defect(self):
        obj = mesh_object()
        obj.scale.x = 1.7
        self.assertEqual(self.inspect(obj)["findings"], [])

    def test_world_units_scaling(self):
        obj = mesh_object()
        obj.scale = (2, 2, 2)
        bpy.context.view_layer.update()
        result = self.inspect(obj)
        self.assertAlmostEqual(result["edge_length_world"]["min"], 4)
        self.assertAlmostEqual(result["shells"][0]["signed_volume_world"], 64)

    def test_small_translated_volume_is_numerically_stable(self):
        obj = mesh_object()
        obj.scale=(.006,.007,.006)
        bpy.context.view_layer.update()
        first=self.inspect(obj)["shells"][0]["signed_volume_world"]
        obj.location=(-3.108,3.66,.74)
        bpy.context.view_layer.update()
        second=self.inspect(obj)["shells"][0]["signed_volume_world"]
        self.assertGreater(second,0)
        self.assertAlmostEqual(first,second,places=14)

    def test_shared_mesh_material_uv_modifiers_hierarchy(self):
        obj = mesh_object("Parent")
        child = bpy.data.objects.new("Child", obj.data)
        bpy.context.scene.collection.objects.link(child)
        child.parent = obj
        obj.data.uv_layers.new(name="UVTest")
        material = bpy.data.materials.new("FixtureMaterial")
        obj.data.materials.append(material)
        mod = child.modifiers.new("Bevel", "BEVEL")
        mod.width, mod.segments = 0.1, 2
        bpy.context.view_layer.update()
        report = ProjectScanner(bpy.context).run()
        records = {o["name"]: o for o in report["objects"]}
        self.assertEqual(records["Child"]["mesh_id"], records["Parent"]["mesh_id"])
        self.assertEqual(records["Child"]["dependencies"]["parent_id"], records["Parent"]["id"])
        self.assertGreater(records["Child"]["evaluated"]["vertices"], records["Child"]["base"]["vertices"])
        self.assertEqual(records["Parent"]["materials"]["uv_maps"][0]["name"], "UVTest")
        self.assertEqual(report["errors"], [])
        atomic_json(ROOT/"examples/inspection.json", report)

    def test_ids_stable_after_rename_in_session(self):
        obj = mesh_object()
        scanner = ProjectScanner(bpy.context)
        first = scanner.ids.get(obj)
        obj.name = "Renamed"
        self.assertEqual(scanner.ids.get(obj), first)

    def test_limits_are_partial_not_pass(self):
        mesh_object()
        result = ProjectScanner(bpy.context, config=InspectionConfig(max_vertices=1)).run()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["objects"][0]["base"]["status"], "skipped_limit")

    def test_selection_and_cancel(self):
        a, b = mesh_object("A"), mesh_object("B")
        a.select_set(True)
        b.select_set(False)
        scanner = ProjectScanner(bpy.context, selected=True)
        self.assertEqual(scanner.total, 1)
        self.assertEqual(scanner.finish(cancelled=True)["status"], "cancelled")

    def test_registration_and_preferences(self):
        register()
        self.assertTrue(hasattr(bpy.context.scene, "mesh_doctor"))
        self.assertEqual(bpy.context.scene.mesh_doctor.max_vertices, 250000)
        unregister()
        self.assertFalse(hasattr(bpy.types.Scene, "mesh_doctor"))

    def test_no_scene_render_mutation(self):
        mesh_object()
        scene = bpy.context.scene
        before = (scene.camera, scene.render.engine, scene.render.resolution_x, scene.view_settings.view_transform)
        ProjectScanner(bpy.context).run()
        self.assertEqual(before, (scene.camera, scene.render.engine, scene.render.resolution_x, scene.view_settings.view_transform))

    def test_invalid_report_rejected(self):
        mesh_object()
        report = ProjectScanner(bpy.context).run()
        report["objects"].append(report["objects"][0])
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_learning_filters_status_units_and_range(self):
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(Path(directory)/"cases.db")
            case = dict(project="synthetic", scope="cube", family="box", units="m",
                        measurements={"width": 2}, method="analytical_box", parameters={"width": 2},
                        problems=[], corrections=[], evidence=["test fixture"], tests=["volume=8"], limitations=["synthetic"],
                        sources=[str(__file__)], technical_status="tested", approval="pending",
                        reusable_rule="Validate manifold and dimensions separately", valid_ranges={"width": [1, 3]})
            store.record(case)
            self.assertEqual(store.candidates("box", "m", {"width": 2}), [])
            case["approval"] = "approved"
            store.record(case)
            self.assertEqual(len(store.candidates("box", "m", {"width": 2})), 1)
            self.assertEqual(store.candidates("box", "mm", {"width": 2}), [])
            self.assertEqual(store.candidates("box", "m", {"width": 5}), [])

    def test_skill_policy_no_arbitrary_caps(self):
        manifest = skill_manifest(Path.home()/".codex/skills")
        self.assertFalse(manifest["policy"]["arbitrary_caps_or_patch_objects"])
        self.assertTrue(all(s["available"] for s in manifest["sources"]))
        atomic_json(ROOT/"examples/skill_manifest.json", manifest)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Integration)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    atomic_json(ROOT/"test-results.json", {"blender": bpy.app.version_string, "tests": result.testsRun,
                "failures": [str(t) + detail for t, detail in result.failures],
                "errors": [str(t) + detail for t, detail in result.errors], "success": result.wasSuccessful()})
    if not result.wasSuccessful():
        raise RuntimeError("Mesh Doctor tests failed")
