"""Unit tests for identity.py — no Blender required."""
import sys
import unittest
from pathlib import Path
from array import array

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_mesh_doctor.identity import (
    IdentityRegistry, measurement_fingerprint, mesh_fingerprint,
)


class _Collection:
    """Wraps a Python list to support len() and foreach_get like bpy collections."""
    def __init__(self, items, extractor):
        self._items = items
        self._extractor = extractor

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def foreach_get(self, attribute, values):
        for i, item in enumerate(self._items):
            vals = self._extractor(item, attribute)
            if type(vals) is list:
                for j, v in enumerate(vals):
                    values[i * len(vals) + j] = v
            else:
                values[i] = vals


def _vertex_co(vertex, attribute):
    if attribute == 'co':
        return list(vertex.co)
    return 0


def _edge_vertices(edge, attribute):
    if attribute == 'vertices':
        return list(edge.vertices)
    if attribute == 'use_edge_sharp':
        return False
    return 0


def _loop_vertex_index(loop, attribute):
    if attribute == 'vertex_index':
        return loop.vertex_index
    return 0


def _poly_loop_start(poly, attribute):
    if attribute == 'loop_start':
        return poly.loop_start
    if attribute == 'loop_total':
        return poly.loop_total
    if attribute == 'use_smooth':
        return True
    return 0


def _make_fake_mesh(vertices_co, edges_verts, polygons_verts):
    """Build a minimal fake mesh with bpy-like collection interface."""
    # Build loops from polygons
    loops = []
    polys = []
    loop_start = 0
    for p in polygons_verts:
        loops.extend(type('L', (), {'vertex_index': vi})() for vi in p)
        polys.append(type('P', (), {
            'vertices': list(p),
            'loop_start': loop_start,
            'loop_total': len(p),
            'use_smooth': True,
        })())
        loop_start += len(p)

    mesh = type('Mesh', (), {})()
    mesh.vertices = _Collection(
        [type('V', (), {'co': c})() for c in vertices_co], _vertex_co)
    mesh.edges = _Collection(
        [type('E', (), {'vertices': list(e)})() for e in edges_verts], _edge_vertices)
    mesh.loops = _Collection(loops, _loop_vertex_index)
    mesh.polygons = _Collection(polys, _poly_loop_start)
    return mesh


class TestMeasurementFingerprint(unittest.TestCase):

    def test_determinism(self):
        v1 = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        e1 = [(0, 1), (1, 2), (2, 0)]
        p1 = [(0, 1, 2)]
        m1 = _make_fake_mesh(v1, e1, p1)
        m2 = _make_fake_mesh(v1, e1, p1)
        self.assertEqual(measurement_fingerprint(m1), measurement_fingerprint(m2))

    def test_vertex_change_changes_hash(self):
        v1 = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
        v2 = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
        m1 = _make_fake_mesh(v1, [], [])
        m2 = _make_fake_mesh(v2, [], [])
        self.assertNotEqual(measurement_fingerprint(m1), measurement_fingerprint(m2))


class TestMeshFingerprint(unittest.TestCase):

    def test_determinism(self):
        v1 = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        e1 = [(0, 1), (1, 2), (2, 0)]
        p1 = [(0, 1, 2)]
        m1 = _make_fake_mesh(v1, e1, p1)
        m2 = _make_fake_mesh(v1, e1, p1)
        self.assertEqual(mesh_fingerprint(m1), mesh_fingerprint(m2))

    def test_connectivity_change_changes_hash(self):
        v1 = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        e1 = [(0, 1), (1, 2)]
        e2 = [(0, 1), (1, 2), (2, 0)]
        m1 = _make_fake_mesh(v1, e1, [])
        m2 = _make_fake_mesh(v1, e2, [])
        self.assertNotEqual(mesh_fingerprint(m1), mesh_fingerprint(m2))


class TestIdentityRegistry(unittest.TestCase):

    def test_get_returns_stable_id(self):
        reg = IdentityRegistry()

        class FakeDatablock:
            bl_rna = type('RNA', (), {'identifier': 'Mesh'})()
            session_uid = 'abc-123'
            def as_pointer(self):
                return 42

        obj = FakeDatablock()
        id1 = reg.get(obj)
        id2 = reg.get(obj)
        self.assertEqual(id1, id2)

    def test_different_objects_get_different_ids(self):
        reg = IdentityRegistry()

        class FakeDatablock:
            bl_rna = type('RNA', (), {'identifier': 'Mesh'})()
            def as_pointer(self):
                return id(self)

        obj1 = FakeDatablock()
        obj1.session_uid = 'uid-1'
        obj2 = FakeDatablock()
        obj2.session_uid = 'uid-2'
        self.assertNotEqual(reg.get(obj1), reg.get(obj2))

    def test_get_none_returns_none(self):
        reg = IdentityRegistry()
        self.assertIsNone(reg.get(None))


if __name__ == '__main__':
    unittest.main()