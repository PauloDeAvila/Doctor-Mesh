"""Eager, bounded numeric input: no lazy ZIP reads inside mesh loops."""
from pathlib import Path
import zipfile
import numpy as np


def load_npz_arrays(path, required=(), max_bytes=512 * 1024 * 1024):
    """Decode each member once, close the archive, return ordinary arrays.

    The budget covers all uncompressed archive members. Object arrays and
    non-finite values are rejected; pickle is never enabled.
    """
    path = Path(path)
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Positive archive byte budget required")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if sum(info.file_size for info in entries) > max_bytes:
            raise ValueError("Uncompressed numeric archive exceeds byte budget")
        if len({info.filename for info in entries}) != len(entries):
            raise ValueError("Duplicate archive member")
        if any(not info.filename.endswith('.npy') for info in entries):
            raise ValueError("Only NPY array members are supported")
    result = {}
    with np.load(path, allow_pickle=False) as archive:
        missing = set(required) - set(archive.files)
        if missing:
            raise ValueError(f"Missing arrays: {sorted(missing)}")
        for name in archive.files:
            value = archive[name]  # Exactly one decompression per array.
            if value.dtype.kind not in 'biuf' or not np.isfinite(value).all():
                raise ValueError(f"Non-finite or non-real numeric array: {name}")
            value.flags.writeable = False
            result[name] = value
    return result


def mesh_arrays(path, max_bytes=512 * 1024 * 1024):
    data = load_npz_arrays(path, ('vertices', 'triangles'), max_bytes)
    vertices, faces = data['vertices'], data['triangles']
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
        raise ValueError("Nonempty Nx3 vertices required")
    if faces.ndim != 2 or faces.shape[1] != 3 or faces.dtype.kind not in 'iu' or not len(faces):
        raise ValueError("Nonempty integer Nx3 triangles required")
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Triangle index outside vertex domain")
    return data


def validate_source_snapshot(mesh, matrix, vertices, expected_matrix, triangles=None):
    """Refuse stale measurements instead of rebuilding from an edited mold."""
    expected=np.asarray(vertices)
    if expected.shape!=(len(mesh.vertices),3):
        raise ValueError('Source topology differs from measured snapshot; remeasure')
    current=np.empty(len(mesh.vertices)*3,np.float64);mesh.vertices.foreach_get('co',current)
    if not np.array_equal(current.reshape(-1,3),expected):
        raise ValueError('Source coordinates changed; remeasure before reusing profiles')
    if triangles is not None:
        mesh.calc_loop_triangles()
        faces=np.empty(len(mesh.loop_triangles)*3,np.int32)
        mesh.loop_triangles.foreach_get('vertices',faces)
        if not np.array_equal(faces.reshape(-1,3),np.asarray(triangles)):
            raise ValueError('Source connectivity/winding changed; remeasure before reusing profiles')
    if not np.array_equal(np.asarray(list(map(list,matrix))),np.asarray(expected_matrix)):
        raise ValueError('Source frame changed; refresh assembly measurements and comparable cameras')
