"""Regression tests for analyze_mesh on canonical meshes with known expected values.

These tests run inside Blender and require bpy, bmesh and mathutils.
Each test builds a canonical mesh, calls analyze_mesh, and asserts
specific known values derived from the geometry.
"""
import json
import unittest
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix

from ai_mesh_doctor.config import InspectionConfig
from ai_mesh_doctor.geometry import analyze_mesh

CONFIG = InspectionConfig()
ROOT = Path(__file__).resolve().parents[1]


def clean_scene():
    """Remove all objects, meshes and materials from Blender data."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)


def make_mesh(name, verts, edges, faces):
    """Create a bpy.types.Mesh from raw pydata."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, faces)
    mesh.update()
    return mesh


def make_bmesh_mesh(name, build):
    """Create a bpy.types.Mesh by building a BMesh then converting it."""
    bm = bmesh.new()
    try:
        build(bm)
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        mesh.update()
        return mesh
    finally:
        bm.free()


class CanonicalMeshRegression(unittest.TestCase):
    def setUp(self):
        clean_scene()

    def tearDown(self):
        clean_scene()

    def inspect(self, mesh, matrix=None):
        if matrix is None:
            matrix = Matrix.Identity(4)
        return analyze_mesh(mesh, matrix, CONFIG)

    def test_unit_cube(self):
        """Unit cube: 8 verts, 12 edges, 6 faces, closed, volume=1, no findings."""
        mesh = make_bmesh_mesh("UnitCube", lambda bm: bmesh.ops.create_cube(bm, size=1))
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["vertices"], 8)
        self.assertEqual(result["edges"], 12)
        self.assertEqual(result["faces"], 6)
        self.assertTrue(result["closed_topology_candidate"])
        self.assertAlmostEqual(result["shells"][0]["signed_volume_world"], 1.0)
        self.assertEqual(result["findings"], [])

    def test_uv_sphere(self):
        """UV sphere: closed, volume > 0, no nonmanifold topology."""
        mesh = make_bmesh_mesh(
            "UVSphere",
            lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0),
        )
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["closed_topology_candidate"])
        self.assertGreater(result["shells"][0]["signed_volume_world"], 0)
        self.assertEqual(result["radial_edge_count"], 0)
        self.assertEqual(result["nonmanifold_vertex_count"], 0)
        self.assertEqual(result["boundary_edge_count"], 0)

    def test_single_triangle(self):
        """Single triangle: not closed, boundary = 3 edges."""
        mesh = make_mesh("Triangle", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["vertices"], 3)
        self.assertEqual(result["edges"], 3)
        self.assertEqual(result["faces"], 1)
        self.assertFalse(result["closed_topology_candidate"])
        self.assertEqual(result["boundary_edge_count"], 3)
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["regions"][0]["edge_count"], 3)
        self.assertTrue(result["regions"][0]["closed_loop"])

    def test_empty_mesh(self):
        """Empty mesh (no vertices): graceful handling, complete status."""
        mesh = make_mesh("Empty", [], [], [])
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["vertices"], 0)
        self.assertEqual(result["edges"], 0)
        self.assertEqual(result["faces"], 0)
        self.assertEqual(result["shells"], [])
        self.assertEqual(result["island_count"], 0)
        self.assertEqual(result["findings"], [])

    def test_degenerate_face(self):
        """Three colinear vertices: face area ~0, degenerate finding."""
        mesh = make_mesh("Degenerate", [(0, 0, 0), (1, 0, 0), (2, 0, 0)], [], [(0, 1, 2)])
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["degenerate_face_count"], 1)
        degenerate = [f for f in result["findings"] if f["type"] == "degenerate_faces"]
        self.assertEqual(len(degenerate), 1)
        self.assertEqual(degenerate[0]["severity"], "error")

    def test_radial_nonmanifold_edge(self):
        """Edge shared by more than 2 faces: radial nonmanifold detection."""

        def build(bm):
            v0 = bm.verts.new((0, 0, 0))
            v1 = bm.verts.new((1, 0, 0))
            v2 = bm.verts.new((0, 1, 0))
            v3 = bm.verts.new((0, -1, 0))
            v4 = bm.verts.new((0, 0, 1))
            bm.faces.new((v0, v1, v2))
            bm.faces.new((v0, v3, v1))
            bm.faces.new((v0, v1, v4))
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

        mesh = make_bmesh_mesh("RadialEdge", build)
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertGreater(result["radial_edge_count"], 0)
        radial = [f for f in result["findings"] if f["type"] == "radial_nonmanifold_edges"]
        self.assertEqual(len(radial), 1)
        self.assertEqual(radial[0]["severity"], "error")

    def test_winding_inconsistency(self):
        """Flipped face on a cube: winding inconsistency detected."""

        def build(bm):
            bmesh.ops.create_cube(bm, size=1)
            bm.faces.ensure_lookup_table()
            bm.faces[0].normal_flip()
            bm.edges.ensure_lookup_table()

        mesh = make_bmesh_mesh("Winding", build)
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertGreater(result["winding_edge_count"], 0)
        winding = [f for f in result["findings"] if f["type"] == "inconsistent_winding"]
        self.assertEqual(len(winding), 1)
        self.assertEqual(winding[0]["severity"], "error")

    def test_loose_vertex(self):
        """Isolated vertex with no edges: loose vertex detection."""

        def build(bm):
            bmesh.ops.create_cube(bm, size=1)
            bm.verts.new((1000, 1000, 1000))

        mesh = make_bmesh_mesh("LooseVertex", build)
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["loose_vertex_count"], 1)
        loose = [f for f in result["findings"] if f["type"] == "loose_vertices"]
        self.assertEqual(len(loose), 1)

    def test_zero_length_edge(self):
        """Edge between two coincident vertices: zero-length edge detection."""

        def build(bm):
            v1 = bm.verts.new((0, 0, 0))
            v2 = bm.verts.new((0, 0, 0))
            bm.edges.new((v1, v2))
            bm.edges.ensure_lookup_table()

        mesh = make_bmesh_mesh("ZeroEdge", build)
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "complete")
        short = [f for f in result["findings"] if f["type"] == "short_edges"]
        self.assertEqual(len(short), 1)

    def test_mirrored_transform(self):
        """Mirrored transform (negative determinant): signed volume negative."""
        mesh = make_bmesh_mesh("MirroredCube", lambda bm: bmesh.ops.create_cube(bm, size=1))
        matrix = Matrix(((-1, 0, 0, 0),
                         (0, 1, 0, 0),
                         (0, 0, 1, 0),
                         (0, 0, 0, 1)))
        self.assertAlmostEqual(matrix.determinant(), -1.0)
        result = self.inspect(mesh, matrix)
        self.assertEqual(result["status"], "complete")
        self.assertLess(result["shells"][0]["signed_volume_world"], 0)
        negative = [f for f in result["findings"] if f["type"] == "negative_shell_volume"]
        self.assertEqual(len(negative), 1)

    def test_nan_coordinates(self):
        """NaN vertex coordinate: invalid_coordinates status."""

        def build(bm):
            bmesh.ops.create_cube(bm, size=1)
            bm.verts[0].co = (float("nan"), 0, 0)

        mesh = make_bmesh_mesh("NaN", build)
        result = self.inspect(mesh)
        self.assertEqual(result["status"], "invalid_coordinates")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CanonicalMeshRegression)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    with open(ROOT / "regression-test-results.json", "w") as handle:
        json.dump(
            {
                "tests": result.testsRun,
                "failures": [str(t) + detail for t, detail in result.failures],
                "errors": [str(t) + detail for t, detail in result.errors],
                "success": result.wasSuccessful(),
            },
            handle,
            indent=2,
        )
    if not result.wasSuccessful():
        raise RuntimeError("Regression tests failed")
