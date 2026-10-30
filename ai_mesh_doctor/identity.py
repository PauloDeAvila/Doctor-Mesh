"""Session IDs do not write custom properties to the user's objects."""
from uuid import uuid4
import hashlib
import struct
from array import array
import sys


class IdentityRegistry:
    def __init__(self):
        self._ids = {}

    def get(self, datablock):
        if datablock is None:
            return None
        # session_uid is stable across renames and Blender undo where supported.
        key = (datablock.bl_rna.identifier, getattr(datablock, "session_uid", datablock.as_pointer()))
        if key not in self._ids:
            self._ids[key] = str(uuid4())
        return self._ids[key]


def measurement_fingerprint(mesh) -> str:
    """Bulk coordinate/connectivity/shading fingerprint; versioned cache input.

    Geometry-only cache entries never stand in for material/UV inspection.
    """
    digest = hashlib.sha256()
    digest.update(b'MD_MESH_V2')
    digest.update(struct.pack('<4Q', len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops)))
    for collection, attribute, kind, count in (
        (mesh.vertices, 'co', 'f', 3*len(mesh.vertices)),
        (mesh.edges, 'vertices', 'I', 2*len(mesh.edges)),
        (mesh.loops, 'vertex_index', 'I', len(mesh.loops)),
        (mesh.polygons, 'loop_start', 'I', len(mesh.polygons)),
        (mesh.polygons, 'loop_total', 'I', len(mesh.polygons)),
        (mesh.edges, 'use_edge_sharp', 'b', len(mesh.edges)),
        (mesh.polygons, 'use_smooth', 'b', len(mesh.polygons)),
    ):
        values = array(kind, [0]) * count
        collection.foreach_get(attribute, values)
        if sys.byteorder != 'little' and values.itemsize > 1:
            values.byteswap()
        digest.update(values.tobytes())
    return digest.hexdigest()


def mesh_fingerprint(mesh) -> str:
    """Preserved 0.1 identity format for stored repair plans and rollback.

    New caches use measurement_fingerprint; changing a cache format must not
    invalidate an existing source-recovery transaction.
    """
    digest = hashlib.sha256()
    for vertex in mesh.vertices:
        digest.update(struct.pack('<3d', *vertex.co))
    for edge in mesh.edges:
        digest.update(struct.pack('<2I', *edge.vertices))
    for polygon in mesh.polygons:
        digest.update(struct.pack('<I', len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack('<I', index))
    return digest.hexdigest()
