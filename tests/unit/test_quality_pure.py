"""Unit tests for pure-Python functions in quality.py (no Blender required)."""
import math
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ---------------------------------------------------------------------------
# Stub mathutils.Vector so quality.py can import without Blender
# ---------------------------------------------------------------------------
class _Vector:
    def __init__(self, x, y=None, z=None):
        if y is None and z is None:
            # Accept a tuple/list
            self.x, self.y, self.z = x[0], x[1], x[2]
        else:
            self.x = x; self.y = y; self.z = z

    @property
    def length(self):
        return math.sqrt(self.x*self.x + self.y*self.y + self.z*self.z)

    def dot(self, other):
        return self.x*other.x + self.y*other.y + self.z*other.z

    def cross(self, other):
        return _Vector(
            self.y*other.z - self.z*other.y,
            self.z*other.x - self.x*other.z,
            self.x*other.y - self.y*other.x,
        )

    def normalized(self):
        L = self.length
        if L <= 0:
            return _Vector(0, 0, 0)
        return _Vector(self.x/L, self.y/L, self.z/L)

    def normalize(self):
        """In-place normalize (Blender mathutils compatibility)."""
        L = self.length
        if L <= 0:
            self.x = self.y = self.z = 0
        else:
            self.x /= L; self.y /= L; self.z /= L

    def __sub__(self, other):
        return _Vector(self.x-other.x, self.y-other.y, self.z-other.z)

    def __add__(self, other):
        return _Vector(self.x+other.x, self.y+other.y, self.z+other.z)

    def __mul__(self, scalar):
        return _Vector(self.x*scalar, self.y*scalar, self.z*scalar)

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __truediv__(self, scalar):
        return _Vector(self.x/scalar, self.y/scalar, self.z/scalar)

    def __getitem__(self, idx):
        return (self.x, self.y, self.z)[idx]

    def __repr__(self):
        return f"_Vector({self.x}, {self.y}, {self.z})"


_mathutils = types.ModuleType('mathutils')
_mathutils.Vector = _Vector
# Stub bvhtree submodule
_bvhtree = types.ModuleType('mathutils.bvhtree')
_bvhtree.BVHTree = type('BVHTree', (), {})
_mathutils.bvhtree = _bvhtree
_kdtree = types.ModuleType('mathutils.kdtree')
_kdtree.KDTree = type('KDTree', (), {})
_mathutils.kdtree = _kdtree
sys.modules['mathutils'] = _mathutils
sys.modules['mathutils.bvhtree'] = _bvhtree
sys.modules['mathutils.kdtree'] = _kdtree

# Stub bpy and bmesh so quality.py can import geometry
_bpy = types.ModuleType('bpy')
_bpy.types = types.SimpleNamespace()
_bpy.types.Mesh = type('Mesh', (), {})
_bpy.types.Object = type('Object', (), {})
sys.modules['bpy'] = _bpy

_bmesh = types.ModuleType('bmesh')
_bmesh.types = types.SimpleNamespace()
_bmesh.types.BMesh = type('BMesh', (), {})
def _bm_new():
    return _bmesh.types.BMesh()
_bmesh.new = _bm_new
_bmesh.ops = types.SimpleNamespace()
sys.modules['bmesh'] = _bmesh

from ai_mesh_doctor.quality_metrics import (
    element_quality_metrics, detect_inverted_faces,
)
from ai_mesh_doctor.quality import QualityPolicy, validate_perfect_mesh


class TestElementQualityMetrics(unittest.TestCase):

    def test_equilateral_triangle(self):
        """Triangulo equilatero: aspect_ratio=1, skewness=0, jacobian=1."""
        points = [_Vector((0, 0, 0)), _Vector((1, 0, 0)), _Vector((0.5, math.sqrt(3)/2, 0))]
        triangles = [(0, 1, 2)]
        normals = [_Vector((0, 0, 1))]
        metrics = element_quality_metrics(points, triangles, normals)
        self.assertAlmostEqual(metrics['aspect_ratio'][0], 1.0, places=5)
        self.assertAlmostEqual(metrics['skewness'][0], 0.0, places=5)
        self.assertAlmostEqual(metrics['jacobian'][0], math.sqrt(3)/2, places=5)
        self.assertAlmostEqual(metrics['internal_angles'][0][0], 60.0, places=5)
        self.assertAlmostEqual(metrics['internal_angles'][0][1], 60.0, places=5)
        self.assertAlmostEqual(metrics['internal_angles'][0][2], 60.0, places=5)

    def test_flat_degenerate_triangle(self):
        """Triangulo com vertices colineares: jacobian=0."""
        points = [_Vector((0, 0, 0)), _Vector((1, 0, 0)), _Vector((2, 0, 0))]
        triangles = [(0, 1, 2)]
        normals = [_Vector((0, 0, 1))]
        metrics = element_quality_metrics(points, triangles, normals)
        self.assertAlmostEqual(metrics['jacobian'][0], 0.0, places=5)

    def test_high_aspect_ratio(self):
        """Triangulo alongado: aspect_ratio alto."""
        points = [_Vector((0, 0, 0)), _Vector((10, 0, 0)), _Vector((0, 0.1, 0))]
        triangles = [(0, 1, 2)]
        normals = [_Vector((0, 0, 1))]
        metrics = element_quality_metrics(points, triangles, normals)
        self.assertGreater(metrics['aspect_ratio'][0], 10.0)

    def test_multiple_triangles(self):
        """Varios triangulos sao processados independentemente."""
        points = [
            _Vector((0, 0, 0)), _Vector((1, 0, 0)), _Vector((0.5, math.sqrt(3)/2, 0)),
            _Vector((0, 0, 0)), _Vector((10, 0, 0)), _Vector((0, 0.1, 0)),
        ]
        triangles = [(0, 1, 2), (3, 4, 5)]
        normals = [_Vector((0, 0, 1)), _Vector((0, 0, 1))]
        metrics = element_quality_metrics(points, triangles, normals)
        self.assertEqual(len(metrics['aspect_ratio']), 2)
        self.assertEqual(len(metrics['skewness']), 2)
        self.assertEqual(len(metrics['jacobian']), 2)


class TestDetectInvertedFaces(unittest.TestCase):

    def test_correct_winding_not_inverted(self):
        """Triangulo com winding correto nao e invertido."""
        points = [_Vector((0, 0, 0)), _Vector((1, 0, 0)), _Vector((0, 1, 0))]
        triangles = [(0, 1, 2)]
        normals = [_Vector((0, 0, 1))]
        inverted = detect_inverted_faces(points, triangles, normals)
        self.assertEqual(inverted, [])

    def test_inverted_winding_detected(self):
        """Triangulo com winding invertido e detectado."""
        points = [_Vector((0, 0, 0)), _Vector((1, 0, 0)), _Vector((0, 1, 0))]
        triangles = [(0, 1, 2)]
        normals = [_Vector((0, 0, -1))]  # Normal oposta ao winding
        inverted = detect_inverted_faces(points, triangles, normals)
        self.assertEqual(inverted, [0])

    def test_multiple_triangles_some_inverted(self):
        """Mixed: alguns invertidos, alguns nao."""
        points = [
            _Vector((0, 0, 0)), _Vector((1, 0, 0)), _Vector((0, 1, 0)),  # correto
            _Vector((0, 0, 0)), _Vector((0, 1, 0)), _Vector((1, 0, 0)),  # invertido
        ]
        triangles = [(0, 1, 2), (3, 4, 5)]
        normals = [_Vector((0, 0, 1)), _Vector((0, 0, 1))]
        inverted = detect_inverted_faces(points, triangles, normals)
        self.assertEqual(inverted, [1])


class TestQualityPolicy(unittest.TestCase):

    def test_defaults(self):
        p = QualityPolicy()
        self.assertIsNone(p.max_aspect_ratio)
        self.assertIsNone(p.min_jacobian)
        self.assertIsNone(p.max_skewness)

    def test_with_thresholds(self):
        p = QualityPolicy(max_aspect_ratio=5.0, min_jacobian=0.3,
                          max_skewness=15.0, min_internal_angle_deg=20.0,
                          max_internal_angle_deg=100.0)
        self.assertEqual(p.max_aspect_ratio, 5.0)
        self.assertEqual(p.min_jacobian, 0.3)

    def test_invalid_negative_threshold(self):
        with self.assertRaises(ValueError):
            QualityPolicy(max_aspect_ratio=-1.0)

    def test_invalid_zero_threshold(self):
        with self.assertRaises(ValueError):
            QualityPolicy(min_jacobian=0.0)

    def test_angle_range_invalid(self):
        with self.assertRaises(ValueError):
            QualityPolicy(min_internal_angle_deg=50.0, max_internal_angle_deg=30.0)


class TestValidatePerfectMesh(unittest.TestCase):

    def test_perfect_mesh(self):
        """Malha limpa: sem defeitos, fechada, volume positivo."""
        report = {
            'status': 'complete',
            'radial_edge_count': 0,
            'nonmanifold_vertex_count': 0,
            'degenerate_face_count': 0,
            'winding_edge_count': 0,
            'loose_vertex_count': 0,
            'loose_edge_count': 0,
            'duplicate_pair_count': 0,
            'self_intersection_count': 0,
            'containment_count': 0,
            'inverted_face_count': 0,
            'boundary_edge_count': 0,
            'closed_topology_candidate': True,
            'shells': [{'closed': True, 'signed_volume_world': 1.0}],
        }
        result = validate_perfect_mesh(report)
        self.assertTrue(result['perfect'])
        self.assertEqual(result['reasons'], [])
        self.assertEqual(result['score'], 1.0)

    def test_self_intersection_fails(self):
        report = {
            'status': 'complete',
            'radial_edge_count': 0, 'nonmanifold_vertex_count': 0,
            'degenerate_face_count': 0, 'winding_edge_count': 0,
            'loose_vertex_count': 0, 'loose_edge_count': 0,
            'duplicate_pair_count': 0,
            'self_intersection_count': 3,  # FALHA
            'containment_count': 0,
            'inverted_face_count': 0,
            'boundary_edge_count': 0,
            'closed_topology_candidate': True,
            'shells': [{'closed': True, 'signed_volume_world': 1.0}],
        }
        result = validate_perfect_mesh(report)
        self.assertFalse(result['perfect'])
        self.assertIn('self_intersections', result['reasons'])
        self.assertLess(result['score'], 1.0)

    def test_incomplete_geometry_fails(self):
        report = {'status': 'skipped_limit'}
        result = validate_perfect_mesh(report)
        self.assertFalse(result['perfect'])
        self.assertIn('geometry_incomplete', result['reasons'])
        self.assertEqual(result['score'], 0.0)

    def test_multiple_defects_accumulate(self):
        report = {
            'status': 'complete',
            'radial_edge_count': 1, 'nonmanifold_vertex_count': 0,
            'degenerate_face_count': 1, 'winding_edge_count': 1,
            'loose_vertex_count': 0, 'loose_edge_count': 0,
            'duplicate_pair_count': 0,
            'self_intersection_count': 0, 'containment_count': 0,
            'inverted_face_count': 0, 'boundary_edge_count': 0,
            'closed_topology_candidate': True,
            'shells': [{'closed': True, 'signed_volume_world': 1.0}],
        }
        result = validate_perfect_mesh(report)
        self.assertFalse(result['perfect'])
        self.assertGreater(len(result['reasons']), 0)
        self.assertLess(result['score'], 1.0)


if __name__ == '__main__':
    unittest.main()