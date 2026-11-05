"""Unit tests for ai_mesh_doctor.arrays (load_npz_arrays, mesh_arrays, validate_source_snapshot).

numpy and bpy are not available in this environment, so numpy is stubbed via
sys.modules before importing the arrays module. Tests focus on the validation
logic that does not require a real numpy implementation.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub numpy before importing arrays so the module imports without the
# optional Blender/numpy dependency.
# ---------------------------------------------------------------------------
_mock_np = MagicMock()
sys.modules["numpy"] = _mock_np

from ai_mesh_doctor import arrays  # noqa: E402  (must import after stubbing numpy)


def _make_npz_file(suffix=".npz"):
    """Create an empty zip archive with an .npy member name (not a real NPY)."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    import zipfile
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("vertices.npy", b"")
        archive.writestr("triangles.npy", b"")
    os_unlink = None
    return path


class TestArraysImport(unittest.TestCase):
    """The arrays module must import cleanly with numpy stubbed."""

    def test_module_imports(self):
        self.assertIsNotNone(arrays)
        self.assertTrue(hasattr(arrays, "load_npz_arrays"))
        self.assertTrue(hasattr(arrays, "mesh_arrays"))
        self.assertTrue(hasattr(arrays, "validate_source_snapshot"))

    def test_numpy_was_stubbed(self):
        self.assertIs(arrays.np, _mock_np)


class TestLoadNpzArraysValidation(unittest.TestCase):
    """Validation that happens before numpy is used (pure-Python checks)."""

    def test_max_bytes_not_int(self):
        with self.assertRaises(ValueError):
            arrays.load_npz_arrays("nonexistent.npz", max_bytes="512")

    def test_max_bytes_zero(self):
        with self.assertRaises(ValueError):
            arrays.load_npz_arrays("nonexistent.npz", max_bytes=0)

    def test_max_bytes_negative(self):
        with self.assertRaises(ValueError):
            arrays.load_npz_arrays("nonexistent.npz", max_bytes=-1)

    def test_nonexistent_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            arrays.load_npz_arrays("nonexistent.npz")


class TestMeshArraysValidation(unittest.TestCase):
    """mesh_arrays delegates to load_npz_arrays; pre-numpy validation applies."""

    def test_max_bytes_validation(self):
        with self.assertRaises(ValueError):
            arrays.mesh_arrays("nonexistent.npz", max_bytes=0)


class TestValidateSourceSnapshotStubbed(unittest.TestCase):
    """validate_source_snapshot uses numpy; with numpy stubbed it should not
    crash on the pure-python shape checks before np.asarray is called.

    We use a stubbed numpy that returns controlled values so the function
    can execute without real arrays.
    """

    def _make_mesh_stub(self, vertex_count=3):
        """A mesh stub whose foreach_get fills a buffer deterministically."""
        class CoStub:
            def __init__(self, count):
                self.count = count

            def __len__(self):
                return self.count

        class MeshStub:
            def __init__(self, count):
                self.vertices = CoStub(count)
                self.loop_triangles = None

            def foreach_get(self, attribute, buffer):
                # Fill buffer with zeros of the right length.
                for i in range(len(buffer)):
                    buffer[i] = 0.0

            def calc_loop_triangles(self):
                self.loop_triangles = type("LT", (), {"foreach_get": lambda self_, buf: None})()

        return MeshStub(vertex_count)

    def test_vertices_shape_mismatch_raises(self):
        mesh = self._make_mesh_stub(vertex_count=3)
        # expected shape is (len(mesh.vertices), 3) = (3, 3); pass (2, 3)
        with self.assertRaises(ValueError):
            arrays.validate_source_snapshot(
                mesh, [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
                [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            )


if __name__ == "__main__":
    unittest.main()
