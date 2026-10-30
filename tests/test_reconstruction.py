import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Matrix
from ai_mesh_doctor.reconstruction import build_component, validate_profile, inspect_neighbors
from ai_mesh_doctor.reporting import atomic_json

ROOT = Path(__file__).resolve().parents[1]


def specification(family="extruded_profile"):
    return {"family": family, "profile": [[-1,-1], [1,-1], [1,1], [-1,1]], "depth": 2,
            "segments": 64, "frame": [list(r) for r in Matrix.Identity(4)], "units": "world_blender_units",
            "measurement_evidence": ["synthetic independent width/height/depth=2"],
            "expected_bounds_local": [[-1,1],[-1,1],[-1,1]], "tolerance": 1e-5,
            "intentional_voids": [], "attachment_points": [[0,0,1]], "neighbor_constraints": {}}


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def test_complete_extruded_solid(self):
        spec = specification()
        obj, report = build_component(spec)
        bpy.context.scene.collection.objects.link(obj)
        self.assertTrue(report["closed_topology_candidate"])
        self.assertAlmostEqual(report["shells"][0]["signed_volume_world"], 8)
        self.assertEqual(report["attachment_points_checked"], 1)
        atomic_json(ROOT/"examples/reconstruction.json", {"specification": spec, "validation": report})

    def test_annular_housing_has_real_inner_wall_and_no_open_edges(self):
        spec = specification("revolved_profile")
        spec["profile"] = [[0.6,-1], [1,-1], [1,1], [0.6,1]]
        spec["intentional_voids"] = ["coaxial bore radius=0.6"]
        spec["attachment_points"] = [[1,0,0]]
        obj, report = build_component(spec)
        self.assertEqual(report["boundary_edge_count"], 0)
        self.assertEqual(report["radial_edge_count"], 0)
        bpy.context.scene.collection.objects.link(obj)

    def test_concave_profile_is_fully_triangulated(self):
        spec = specification()
        spec["profile"] = [[-1,-1], [1,-1], [1,0], [0,0], [0,1], [-1,1]]
        spec["attachment_points"] = [[-0.5,0.5,1]]
        obj, report = build_component(spec)
        bpy.context.scene.collection.objects.link(obj)
        self.assertAlmostEqual(report["shells"][0]["signed_volume_world"], 6)

    def test_ambiguous_or_invalid_profiles_rejected(self):
        for profile in ([[0,0],[1,1],[0,1],[1,0]], [[0,0],[1,0],[2,0]], [[0,0],[0,0],[1,1]]):
            with self.assertRaises(ValueError):
                validate_profile(profile)

    def test_wrong_independent_dimensions_rejected(self):
        spec = specification()
        spec["expected_bounds_local"][0] = [-2,2]
        with self.assertRaises(ValueError):
            build_component(spec)

    def test_wrong_attachment_rejected(self):
        spec = specification()
        spec["attachment_points"] = [[0,0,4]]
        with self.assertRaises(ValueError):
            build_component(spec)

    def test_neighbor_intersection_and_containment_are_not_silently_accepted(self):
        spec = specification()
        candidate, _ = build_component(spec)
        bpy.context.scene.collection.objects.link(candidate)
        bpy.ops.mesh.primitive_cube_add(size=0.3)
        contained = bpy.context.object
        contained.name = "Contained"
        bpy.ops.mesh.primitive_cube_add(location=(1,0,0))
        crossing = bpy.context.object
        crossing.name = "Crossing"
        report = inspect_neighbors(bpy.context, candidate, None, spec)
        by_name = {p["neighbor"]: p for p in report["pairs"]}
        self.assertEqual(by_name["Crossing"]["result"], "surface_overlap")
        self.assertEqual(by_name["Contained"]["result"], "containment_candidate")
        self.assertEqual(report["unclassified"], 2)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReconstructionTests))
    atomic_json(ROOT/"reconstruction-test-results.json", {"tests": result.testsRun, "success": result.wasSuccessful(),
                "failures": [str(t)+d for t,d in result.failures], "errors": [str(t)+d for t,d in result.errors]})
    if not result.wasSuccessful():
        raise RuntimeError("Reconstruction tests failed")
