import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import bmesh
from ai_mesh_doctor.scanner import ProjectScanner
from ai_mesh_doctor.repair import RepairTransaction, rollback, measured_plane
from ai_mesh_doctor.planning import deterministic_plan
from ai_mesh_doctor.identity import mesh_fingerprint
from ai_mesh_doctor.reporting import atomic_json

ROOT = Path(__file__).resolve().parents[1]


class RepairTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object

    def flipped(self):
        bm = bmesh.new()
        bm.from_mesh(self.obj.data)
        bm.faces.ensure_lookup_table()
        bm.faces[0].normal_flip()
        bm.to_mesh(self.obj.data)
        bm.free()

    def transaction(self, operation="recalculate_normals", parameters=None, **constraints):
        report = ProjectScanner(bpy.context).run()
        record = next(o for o in report["objects"] if o["name"] == self.obj.name)
        limits = {"max_displacement": 0.001, "max_dimension_delta": 0.001,
                  "max_topology_delta": 0, "protected_vertices": []}
        limits.update(constraints)
        plan = deterministic_plan(record, operation, list(range(len(self.obj.data.vertices))), parameters or {}, limits, "Synthetic repair")
        return RepairTransaction(bpy.context, self.obj, plan, report)

    def test_preview_apply_and_rollback(self):
        self.flipped()
        original = self.obj.data
        signature = mesh_fingerprint(original)
        material = bpy.data.materials.new("Preserved")
        original.materials.append(material)
        original.uv_layers.new(name="PreservedUV")
        transaction = self.transaction()
        self.assertIs(self.obj.data, original)
        self.assertEqual(mesh_fingerprint(original), signature)
        self.assertEqual(transaction.validation["after"]["winding_edge_count"], 0)
        with self.assertRaises(ValueError):
            transaction.apply()
        transaction.apply(approved=True)
        self.assertIsNot(self.obj.data, original)
        self.assertIn("PreservedUV", self.obj.data.uv_layers)
        self.assertEqual(self.obj.data.materials[0], material)
        atomic_json(ROOT/"examples/repair.json", {"plan": transaction.plan, "validation": transaction.validation})
        rollback(self.obj)
        self.assertIs(self.obj.data, original)
        self.assertEqual(mesh_fingerprint(self.obj.data), signature)

    def test_clean_mesh_rejected_as_unnecessary(self):
        with self.assertRaises(ValueError):
            self.transaction()

    def test_stale_preview_blocked(self):
        self.flipped()
        transaction = self.transaction()
        self.obj.data.vertices[0].co.x += 0.2
        with self.assertRaises(ValueError):
            transaction.apply(approved=True)
        transaction.discard()

    def test_shared_source_not_changed(self):
        self.flipped()
        second = self.obj.copy()
        bpy.context.scene.collection.objects.link(second)
        original = second.data
        transaction = self.transaction()
        transaction.apply(approved=True)
        self.assertIs(second.data, original)
        self.assertIsNot(second.data, self.obj.data)

    def test_plane_correction_and_displacement_limit(self):
        mesh = bpy.data.meshes.new("Plane")
        mesh.from_pydata([(0,0,0), (1,0,0), (1,1,0.1), (0,1,0)], [], [(0,1,2,3)])
        self.obj.data = mesh
        fit = measured_plane(self.obj, list(range(4)))
        parameters = {"origin": fit["origin"], "normal": fit["normal"], "strength": 1}
        with self.assertRaises(ValueError):
            self.transaction("fit_plane", parameters, max_displacement=0)
        transaction = self.transaction("fit_plane", parameters, max_displacement=0.2, max_dimension_delta=0.2)
        self.assertTrue(transaction.validation["accepted"])
        transaction.discard()

    def test_uv_change_after_preview_blocks_apply(self):
        self.flipped()
        layer = self.obj.data.uv_layers.new()
        transaction = self.transaction()
        layer.data[0].uv.x = 0.312
        with self.assertRaises(ValueError):
            transaction.apply(approved=True)
        transaction.discard()

    def test_duplicate_merge_requires_explicit_topology_budget(self):
        bm = bmesh.new()
        bm.from_mesh(self.obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts.new(bm.verts[0].co)
        bm.to_mesh(self.obj.data)
        bm.free()
        with self.assertRaises(ValueError):
            self.transaction("merge_vertices", {"distance": 1e-6})
        transaction = self.transaction("merge_vertices", {"distance": 1e-6}, max_topology_delta=10)
        self.assertEqual(transaction.validation["after"]["duplicate_pair_count"], 0)
        transaction.discard()

    def test_loose_removal(self):
        bm = bmesh.new()
        bm.from_mesh(self.obj.data)
        bm.verts.new((4,4,4))
        bm.to_mesh(self.obj.data)
        bm.free()
        transaction = self.transaction("remove_loose", {}, max_topology_delta=10, max_dimension_delta=10)
        self.assertEqual(transaction.validation["after"]["loose_vertex_count"], 0)
        transaction.discard()

    def grid(self, noisy=False):
        mesh = bpy.data.meshes.new("Grid")
        coords = [(x,y,0) for y in range(3) for x in range(3)]
        coords[4] = (1,1,0.1) if noisy else (1.2,1.1,0)
        mesh.from_pydata(coords, [], [(y*3+x,y*3+x+1,(y+1)*3+x+1,(y+1)*3+x) for y in range(2) for x in range(2)])
        self.obj.data = mesh

    def test_local_smoothing_preserves_open_boundary(self):
        self.grid(noisy=True)
        transaction = self.transaction("smooth_local", {"strength": 0.5, "iterations": 1}, max_displacement=0.2, max_dimension_delta=0.2)
        self.assertLess(transaction.validation["fairness_energy_after"], transaction.validation["fairness_energy_before"])
        for i in (0,1,2,3,5,6,7,8):
            self.assertEqual(tuple(transaction.work.vertices[i].co), tuple(self.obj.data.vertices[i].co))
        transaction.discard()

    def test_tangential_relaxation(self):
        self.grid()
        transaction = self.transaction("relax_local", {"strength": 0.5, "iterations": 1}, max_displacement=0.3, max_dimension_delta=0.2)
        self.assertAlmostEqual(transaction.work.vertices[4].co.z, 0)
        self.assertLess(transaction.validation["fairness_energy_after"], transaction.validation["fairness_energy_before"])
        transaction.discard()

    def test_rollback_rejects_unrecorded_edits(self):
        self.flipped()
        transaction = self.transaction()
        transaction.apply(approved=True)
        self.obj.data.vertices[0].co.x += 0.2
        with self.assertRaises(ValueError):
            rollback(self.obj)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RepairTests))
    atomic_json(ROOT/"repair-test-results.json", {"tests": result.testsRun, "success": result.wasSuccessful(),
                "failures": [str(t)+d for t,d in result.failures], "errors": [str(t)+d for t,d in result.errors]})
    if not result.wasSuccessful():
        raise RuntimeError("Repair tests failed")
