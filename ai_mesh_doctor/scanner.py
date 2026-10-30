import time
import copy
from uuid import uuid4
import bpy
from mathutils import Vector
from .config import InspectionConfig
from .identity import IdentityRegistry, measurement_fingerprint
from .geometry import analyze_mesh
from .dependencies import inspect_dependencies
from .materials import inspect_materials
from .reporting import SCHEMA_VERSION, utc_now, validate_report
from .cache import MeasurementCache, content_key


class ProjectScanner:
    """Call step() on Blender's main thread; one object per UI timer tick."""
    def __init__(self, context, selected=False, config=None, cache_directory=None):
        if context.mode != "OBJECT":
            raise ValueError("Switch to Object Mode before scanning; edit buffers are not silently committed")
        self.config = config or InspectionConfig()
        self.ids = IdentityRegistry()
        self.geometry_cache = {}
        self.persistent_cache = MeasurementCache(cache_directory) if cache_directory else None
        self.cache_hits = self.analysis_runs = 0
        self.context = context
        self.queue = sorted(list(context.selected_objects if selected else context.scene.objects), key=lambda o: o.name_full)
        self.total = len(self.queue)
        self.position = 0
        self.started = time.monotonic()
        self.depsgraph = context.evaluated_depsgraph_get()
        self.report = {
            "schema_version": SCHEMA_VERSION, "session_id": str(uuid4()), "created_at": utc_now(),
            "status": "running", "source": bpy.data.filepath, "blender_version": bpy.app.version_string,
            "units": {"system": context.scene.unit_settings.system, "scale_length": context.scene.unit_settings.scale_length,
                      "metric_space": "world_blender_units", "meters_per_world_unit": context.scene.unit_settings.scale_length},
            "config": self.config.to_dict(), "selected_only": selected, "objects": [], "errors": [],
            "collections": self._collections(context.scene.collection),
            "coverage": {"scope": "active_scene", "other_scenes": "not_scanned", "external_libraries": "metadata_only",
                         "instances": "source_metadata_and_depsgraph_inventory", "geometry_mutated": False},
            "instances": [{"object_id": self.ids.get(i.object.original), "is_instance": i.is_instance,
                           "world_matrix": [list(row) for row in i.matrix_world],
                           "parent_id": self.ids.get(i.parent.original) if i.parent else None}
                          for i in self.depsgraph.object_instances],
        }

    def _collections(self, collection):
        return {"id": self.ids.get(collection), "name": collection.name_full,
                "objects": [self.ids.get(o) for o in collection.objects],
                "children": [self._collections(c) for c in collection.children]}

    def step(self):
        if self.position >= self.total:
            return False
        if time.monotonic() - self.started > self.config.max_seconds:
            self.report["errors"].append({"reason": "Session time budget exceeded", "remaining": self.total-self.position})
            self.report["status"] = "partial"
            self.position = self.total
            return False
        obj = self.queue[self.position]
        self.position += 1
        try:
            self.report["objects"].append(self.inspect_object(obj))
        except Exception as exc:
            self.report["errors"].append({"object_id": self.ids.get(obj), "name": obj.name_full,
                                          "type": type(exc).__name__, "reason": str(exc)})
        return self.position < self.total

    def inspect_object(self, obj):
        bounds = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        record = {
            "id": self.ids.get(obj), "name": obj.name_full, "type": obj.type,
            "collections": [c.name_full for c in obj.users_collection],
            "world_matrix": [list(row) for row in obj.matrix_world],
            "local_matrix": [list(row) for row in obj.matrix_local],
            "world_bounds": {"min": [min(v[i] for v in bounds) for i in range(3)],
                             "max": [max(v[i] for v in bounds) for i in range(3)]},
            "dimensions": list(obj.dimensions), "scale": list(obj.scale),
            "world_determinant": obj.matrix_world.determinant(),
            "visible": obj.visible_get(), "hide_render": obj.hide_render,
            "editable": obj.is_editable, "dependencies": inspect_dependencies(obj, self.ids),
        }
        if obj.type == "MESH":
            geometry = self._geometry(obj.data, obj.matrix_world)
            record.update(mesh_id=self.ids.get(obj.data), mesh_users=obj.data.users,
                          materials=inspect_materials(obj), base=geometry)
            if self.config.inspect_evaluated:
                evaluated = obj.evaluated_get(self.depsgraph)
                mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=self.depsgraph)
                try:
                    record["evaluated"] = self._geometry(mesh, evaluated.matrix_world)
                    record["evaluated"]["index_mapping"] = "Independent domain; indices cannot target base mesh"
                finally:
                    evaluated.to_mesh_clear()
        return record

    def _geometry(self, mesh, matrix):
        # Compare actual evaluated CONTENT, never temporary pointers. A modifier
        # may change while leaving the source datablock and pointer untouched.
        key = content_key('geometry-v3-local-origin', {'mesh': measurement_fingerprint(mesh),
            'matrix': [list(row) for row in matrix], 'config': self.config.to_dict(),
            'blender': bpy.app.version_string,
            'unit_scale': self.context.scene.unit_settings.scale_length})
        if key in self.geometry_cache:
            self.cache_hits += 1
            return copy.deepcopy(self.geometry_cache[key])
        report = self.persistent_cache.get(key) if self.persistent_cache else None
        if report is None:
            report = analyze_mesh(mesh, matrix, self.config)
            self.analysis_runs += 1
            if self.persistent_cache:
                self.persistent_cache.put(key, report)
        else:
            self.cache_hits += 1
        if report.get('status') == 'complete':
            self.geometry_cache[key] = copy.deepcopy(report)
        return copy.deepcopy(report)

    def finish(self, cancelled=False):
        self.report["finished_at"] = utc_now()
        if cancelled:
            self.report["status"] = "cancelled"
        elif self.report["status"] == "running":
            incomplete = any(o.get(domain, {}).get("status", "complete") != "complete"
                             for o in self.report["objects"] for domain in ("base", "evaluated"))
            self.report["status"] = "partial" if self.report["errors"] or incomplete else "complete"
        self.report["summary"] = {
            "objects": len(self.report["objects"]), "mesh_objects": sum(o["type"] == "MESH" for o in self.report["objects"]),
            "base_findings": sum(len(o.get("base", {}).get("findings", [])) for o in self.report["objects"]),
            "errors": len(self.report["errors"]), "elapsed_seconds": time.monotonic()-self.started,
            "geometry_analysis_runs": self.analysis_runs, "geometry_cache_hits": self.cache_hits,
        }
        return validate_report(self.report)

    def run(self):
        while self.step():
            pass
        return self.finish()
