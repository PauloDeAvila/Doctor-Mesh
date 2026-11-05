"""Repairs run exclusively on copied meshes; apply swaps a datablock after review."""
import json
import math
from uuid import uuid4
import hashlib
import bpy
import bmesh
from mathutils import Vector
from .identity import mesh_fingerprint
from .planning import validate_plan
from .reporting import utc_now
from .validation import validate_change
from .dependencies import rna_settings
from .mesh_simplify import simplify_edge_collapse
from .mesh_subdivide import subdivide_loop


def state_signature(obj):
    """Also guards UVs, attributes, material slots and scene relationships."""
    mesh = obj.data
    attributes = []
    for attribute in mesh.attributes:
        samples = []
        for element in attribute.data:
            entry = {}
            for prop in element.bl_rna.properties:
                if prop.identifier == "rna_type":
                    continue
                if prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
                    value = getattr(element, prop.identifier)
                    entry[prop.identifier] = list(value) if prop.is_array else value
            samples.append(entry)
        attributes.append((attribute.name, attribute.domain, attribute.data_type, samples))
    content = {"geometry": mesh_fingerprint(mesh), "attributes": attributes,
               "matrix": [list(r) for r in obj.matrix_world],
               "materials": [(s.material.as_pointer() if s.material else None, s.link) for s in obj.material_slots],
               "parent": obj.parent.as_pointer() if obj.parent else None,
               "modifiers": [(m.type, rna_settings(m)) for m in obj.modifiers],
               "constraints": [(c.type, rna_settings(c)) for c in obj.constraints],
               "polygons": [(p.material_index, p.use_smooth) for p in mesh.polygons]}
    return hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False).encode()).hexdigest()


def measured_plane(obj, indices):
    import numpy as np
    points = np.array([tuple(obj.matrix_world @ obj.data.vertices[i].co) for i in indices], dtype=float)
    if len(points) < 3:
        raise ValueError("A plane requires at least three vertices")
    center = points.mean(axis=0)
    values, vectors = np.linalg.eigh((points-center).T @ (points-center))
    if values[1] <= 1e-16:
        raise ValueError("Selected points are collinear; plane is ambiguous")
    return {"origin": center.tolist(), "normal": vectors[:,0].tolist(),
            "rms_world": math.sqrt(max(0, values[0])/len(points))}


def _operate(mesh, matrix, plan):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        provenance = bm.verts.layers.int.new("_md_source_index")
        for v in bm.verts:
            v[provenance] = v.index
        region = {bm.verts[i] for i in plan["region"]}
        operation, params = plan["operation"], plan["parameters"]
        # Work directly in world space, correctly handling nonuniform scale.
        inverse = matrix.inverted()
        bm.transform(matrix)
        bm.normal_update()
        if operation == "recalculate_normals":
            faces = [f for f in bm.faces if all(v in region for v in f.verts)]
            if not faces:
                raise ValueError("Region contains no complete faces")
            bmesh.ops.recalc_face_normals(bm, faces=faces)
        elif operation == "merge_vertices":
            bmesh.ops.remove_doubles(bm, verts=list(region), dist=params["distance"])
        elif operation == "remove_loose":
            edges = [e for e in bm.edges if e.is_wire and all(v in region for v in e.verts)]
            bmesh.ops.delete(bm, geom=edges, context="EDGES")
            isolated = [v for v in bm.verts if v in region and not v.link_edges]
            bmesh.ops.delete(bm, geom=isolated, context="VERTS")
        elif operation == "fit_plane":
            normal, origin = Vector(params["normal"]).normalized(), Vector(params["origin"])
            for vertex in region:
                vertex.co -= normal*(vertex.co-origin).dot(normal)*params["strength"]
        elif operation in {"smooth_local", "relax_local"}:
            movable = [v for v in region if v.link_edges and not v.is_boundary and
                       all(e.other_vert(v) in region and e.smooth and (not e.is_manifold or e.calc_face_angle(0) < math.radians(30)) for e in v.link_edges)]
            if not movable:
                raise ValueError("No interior vertices remain after protecting boundaries and hard features")
            for _ in range(params["iterations"]):
                updates = {}
                for v in movable:
                    average = sum((e.other_vert(v).co for e in v.link_edges), Vector())/len(v.link_edges)
                    delta = (average-v.co)*params["strength"]
                    if operation == "relax_local":
                        delta -= v.normal*delta.dot(v.normal)
                    updates[v] = v.co+delta
                for v, coordinate in updates.items():
                    v.co = coordinate
                bm.normal_update()
        elif operation == "fill_holes":
            bm.edges.ensure_lookup_table()
            boundary = [e for e in bm.edges if e.is_boundary]
            if not boundary:
                raise ValueError("No boundary holes to fill")
            # Group boundary edges into loops with ordered vertices
            remaining = set(boundary)
            loops = []
            while remaining:
                start = remaining.pop()
                loop_edges = [start]
                # Walk the loop: from each edge, find the next edge sharing a vertex
                current_edge = start
                while True:
                    found_next = False
                    for v in current_edge.verts:
                        for adj in v.link_edges:
                            if adj in remaining and adj != current_edge:
                                # Check if this edge continues the loop (shares exactly one vertex)
                                shared = set(current_edge.verts) & set(adj.verts)
                                if len(shared) == 1:
                                    remaining.remove(adj)
                                    loop_edges.append(adj)
                                    current_edge = adj
                                    found_next = True
                                    break
                        if found_next:
                            break
                    if not found_next:
                        break
                    if current_edge == start:
                        break
                loops.append(loop_edges)
            # Create faces from each ordered loop
            for loop_edges in loops:
                # Build ordered vertex list by walking the loop
                if len(loop_edges) < 3:
                    continue
                # Start with first edge's vertices
                first_edge = loop_edges[0]
                v_start, v_next = first_edge.verts
                ordered_verts = [v_start, v_next]
                # Walk remaining edges to build ordered vertex list
                used_edges = {first_edge}
                current_v = v_next
                while len(ordered_verts) < len(loop_edges) + 1:
                    found = False
                    for e in loop_edges:
                        if e in used_edges:
                            continue
                        if current_v in e.verts:
                            other = e.other_vert(current_v)
                            if other not in ordered_verts or other == v_start:
                                ordered_verts.append(other)
                                used_edges.add(e)
                                current_v = other
                                found = True
                                break
                    if not found:
                        break
                # Remove duplicate closing vertex if present
                if len(ordered_verts) > 1 and ordered_verts[0] == ordered_verts[-1]:
                    ordered_verts = ordered_verts[:-1]
                if len(ordered_verts) >= 3:
                    try:
                        bm.faces.new(ordered_verts)
                    except Exception:
                        pass
        elif operation == "fix_nonmanifold":
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            merge_dist = params.get("merge_distance", 1e-6)
            radial = [e for e in bm.edges if len(e.link_faces) > 2]
            if not radial:
                raise ValueError("No non-manifold radial edges to fix")
            # Separate faces at radial edges by duplicating vertices
            # Simple approach: merge vertices within merge_dist to collapse duplicates
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=merge_dist)
            # Re-check after merge
            bm.normal_update()
            radial_after = [e for e in bm.edges if len(e.link_faces) > 2]
            if radial_after:
                # If still non-manifold, delete the extra faces (conservative)
                faces_to_delete = set()
                for e in radial_after:
                    for f in e.link_faces:
                        faces_to_delete.add(f)
                if faces_to_delete:
                    bmesh.ops.delete(bm, geom=list(faces_to_delete), context="FACES")
        elif operation == "remove_degenerate":
            area_tol = params.get("area_tolerance", 1e-12)
            bm.faces.ensure_lookup_table()
            degenerate = [f for f in bm.faces if f.calc_area() <= area_tol]
            if not degenerate:
                raise ValueError("No degenerate faces to remove")
            bmesh.ops.delete(bm, geom=degenerate, context="FACES")
        elif operation == "fix_inverted_normals":
            bm.faces.ensure_lookup_table()
            inverted = []
            for f in bm.faces:
                if len(f.verts) < 3:
                    continue
                v0, v1, v2 = f.verts[0].co, f.verts[1].co, f.verts[2].co
                computed = (v1 - v0).cross(v2 - v0)
                if computed.length < 1e-12:
                    continue
                computed.normalize()
                if computed.dot(f.normal) < 0:
                    inverted.append(f)
            if not inverted:
                raise ValueError("No inverted faces to fix")
            bmesh.ops.recalc_face_normals(bm, faces=inverted)
        elif operation == "simplify_qem":
            target_ratio = params.get("target_ratio", 0.5)
            max_iter = params.get("max_iterations", None)
            n = simplify_edge_collapse(bm, target_ratio=target_ratio,
                                       protect_boundary=True,
                                       protect_sharp=True,
                                       max_iterations=max_iter)
            if n == 0:
                raise ValueError("No edges could be collapsed")
        elif operation == "subdivide_loop":
            iterations = params.get("iterations", 1)
            n = subdivide_loop(bm, iterations=iterations, protect_boundary=True)
            if n <= len(bm.faces):
                raise ValueError("Subdivision did not increase face count")
        else:
            raise ValueError("Operation is not registered")
        mapping = [v[provenance] for v in bm.verts]
        bm.verts.layers.int.remove(provenance)
        bm.transform(inverse)
        bm.normal_update()
        bm.to_mesh(mesh)
        mesh.update()
        return mapping
    finally:
        bm.free()


class RepairTransaction:
    def __init__(self, context, obj, plan, report):
        record = validate_plan(plan, report)
        if obj.type != "MESH" or obj.name_full != record["name"] or mesh_fingerprint(obj.data) != plan["fingerprint"]:
            raise ValueError("Scene target changed since scan")
        if not obj.is_editable or not obj.data.is_editable or obj.data.shape_keys or context.mode != "OBJECT":
            raise ValueError("Editable Object Mode mesh without shape keys is required")
        if obj.data.has_custom_normals:
            raise ValueError("Custom split normals require a dedicated preservation workflow")
        if abs(obj.matrix_world.determinant()) < 1e-12:
            raise ValueError("Singular transform")
        if any(m.type in {"MULTIRES", "NODES"} for m in obj.modifiers):
            raise ValueError("Multires/Geometry Nodes reconstruction dependencies require manual review")
        self.id = str(uuid4())
        self.obj = obj
        self.plan = plan
        self.source_signature = state_signature(obj)
        self.source_mesh = obj.data
        self.work = obj.data.copy()
        self.work.name = f"MD_WORK_{self.id}"
        self.preview = None
        self.state = "created"
        try:
            mapping = _operate(self.work, obj.matrix_world, plan)
            self.validation = validate_change(obj.data, self.work, obj.matrix_world, mapping,
                                              plan["region"], plan["constraints"], plan["operation"])
            if not self.validation["accepted"]:
                raise ValueError("Repair rejected: " + "; ".join(self.validation["reasons"]))
            if plan["operation"] == "fit_plane":
                normal, origin = Vector(plan["parameters"]["normal"]).normalized(), Vector(plan["parameters"]["origin"])
                def residual(mesh):
                    return sum(((obj.matrix_world @ mesh.vertices[i].co-origin).dot(normal))**2 for i in plan["region"])
                if residual(self.work) >= residual(obj.data)-1e-20:
                    raise ValueError("Planar residual did not improve")
            if plan["operation"] in {"smooth_local", "relax_local"}:
                def energy(mesh):
                    bm = bmesh.new()
                    try:
                        bm.from_mesh(mesh)
                        bm.transform(obj.matrix_world)
                        bm.normal_update()
                        bm.verts.ensure_lookup_table()
                        total = 0.0
                        for index in plan["region"]:
                            vertex = bm.verts[index]
                            if vertex.link_edges and not vertex.is_boundary:
                                delta = sum((e.other_vert(vertex).co for e in vertex.link_edges), Vector())/len(vertex.link_edges)-vertex.co
                                if plan["operation"] == "relax_local":
                                    delta -= vertex.normal*delta.dot(vertex.normal)
                                total += delta.length_squared
                        return total
                    finally:
                        bm.free()
                self.validation["fairness_energy_before"] = energy(obj.data)
                self.validation["fairness_energy_after"] = energy(self.work)
                if self.validation["fairness_energy_after"] >= self.validation["fairness_energy_before"]-1e-20:
                    raise ValueError("Local fairness metric did not improve")
            self.preview = obj.copy()
            self.preview.data = self.work
            self.preview.name = f"MD_PREVIEW_{obj.name}"
            self.preview["mesh_doctor_transaction"] = self.id
            context.scene.collection.objects.link(self.preview)
            self.preview.hide_render = True
            self.preview.hide_set(True)
            self.preview_signature = state_signature(self.preview)
            self.state = "previewed"
        except Exception:
            self.discard()
            raise

    def apply(self, approved=False):
        if not approved:
            raise ValueError("Explicit approval of the preview is required")
        if self.state != "previewed" or state_signature(self.obj) != self.source_signature:
            raise ValueError("Source changed; rescan and build a new preview")
        if state_signature(self.preview) != self.preview_signature:
            raise ValueError("Preview changed after validation")
        source_fake_user = self.source_mesh.use_fake_user
        self.source_mesh.use_fake_user = True
        history = json.loads(self.obj.get("mesh_doctor_history", "[]"))
        history.append({"id": self.id, "source_mesh": self.source_mesh.name,
                        "result_mesh": self.work.name, "source_fake_user": bool(source_fake_user),
                        "source_signature": self.source_signature, "plan": self.plan, "created_at": utc_now()})
        self.obj.data = self.work
        history[-1]["result_signature"] = state_signature(self.obj)
        self.obj["mesh_doctor_history"] = json.dumps(history)
        if self.preview:
            bpy.data.objects.remove(self.preview, do_unlink=True)
            self.preview = None
        self.state = "applied"
        return self.validation

    def discard(self):
        if self.preview:
            bpy.data.objects.remove(self.preview, do_unlink=True)
            self.preview = None
        if self.work and self.work.users == 0:
            bpy.data.meshes.remove(self.work)
            self.work = None
        self.state = "discarded"


def rollback(obj):
    history = json.loads(obj.get("mesh_doctor_history", "[]"))
    if not history:
        raise ValueError("No recorded repair to roll back")
    last = history[-1]
    source = bpy.data.meshes.get(last["source_mesh"])
    if source is None or obj.data.name != last["result_mesh"]:
        raise ValueError("Recovery datablock missing or object has changed")
    if state_signature(obj) != last["result_signature"]:
        raise ValueError("Current result was edited after repair; preserve those edits before rollback")
    result_mesh = obj.data
    obj.data = source
    source.use_fake_user = last["source_fake_user"]
    obj["mesh_doctor_history"] = json.dumps(history[:-1])
    if result_mesh.users == 0:
        bpy.data.meshes.remove(result_mesh)
    return last
