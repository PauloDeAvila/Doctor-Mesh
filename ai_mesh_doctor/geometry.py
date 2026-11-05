"""World-unit measurements on a disposable BMesh with a nearby local origin.

Candidates are observations, never a claim that artistic intent is defective.
"""
import math
import time
from collections import Counter
import bmesh
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree
from .identity import mesh_fingerprint


def stats(values):
    values = list(values)
    return {"min": min(values), "max": max(values), "mean": sum(values) / len(values)} if values else None


def point_inside_mesh(mesh, matrix, point, epsilon=1e-6, max_rays=2048):
    """Ray-casting point-inside-mesh test with multiple directions.

    Casts rays from the point in several non-coplanar directions and counts
    face crossings. Odd count in all directions => inside; even in all =>
    outside; mixed => unknown (point on surface or degenerate case).

    Parameters
    ----------
    mesh : bpy.types.Mesh
    matrix : mathutils.Matrix (world transform of the mesh)
    point : mathutils.Vector (world-space query point)
    epsilon : float (offset step after each hit to avoid self-intersection)
    max_rays : int (max ray cast steps per direction)

    Returns
    -------
    str : "inside", "outside", or "unknown"
    """
    from mathutils import Vector
    # Build BVH of world-space triangles
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.transform(matrix)
        bm.normal_update()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        points = [v.co for v in bm.verts]
        triangles = [tuple(v.index for v in f.verts) for f in bm.faces if len(f.verts) == 3]
        # Triangulate n-gons
        for f in bm.faces:
            if len(f.verts) > 3:
                verts = list(f.verts)
                for i in range(1, len(verts) - 1):
                    triangles.append((verts[0].index, verts[i].index, verts[i + 1].index))
        tree = BVHTree.FromPolygons(points, triangles)
    finally:
        bm.free()

    directions = [
        Vector((1.0, 0.371, 0.217)).normalized(),
        Vector((0.173, 1.0, 0.419)).normalized(),
        Vector((0.319, 0.127, 1.0)).normalized(),
        Vector((-1.0, 0.5, -0.3)).normalized(),
    ]
    votes = []
    for direction in directions:
        count = 0
        origin = point.copy()
        hit_any = False
        for _ in range(max_rays):
            location, normal, index, distance = tree.ray_cast(origin, direction)
            if location is None:
                break
            count += 1
            hit_any = True
            origin = location + direction * epsilon
        else:
            # Maxed out without escaping: treat as unknown
            votes.append("unknown")
            continue
        if not hit_any:
            votes.append("outside")
        else:
            votes.append("inside" if count % 2 == 1 else "outside")

    if all(v == "inside" for v in votes):
        return "inside"
    if all(v == "outside" for v in votes):
        return "outside"
    return "unknown"


def connected_components(vertices):
    remaining = set(vertices)
    islands = []
    while remaining:
        start = remaining.pop()
        component, stack = [start], [start]
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    stack.append(other)
                    component.append(other)
        islands.append(component)
    return islands


def boundary_regions(edges, cap):
    remaining = set(edges)
    regions = []
    while remaining:
        edge = min(remaining, key=lambda item: item.index)
        remaining.remove(edge)
        group, stack = [edge], [edge]
        while stack:
            for vertex in stack.pop().verts:
                for adjacent in vertex.link_edges:
                    if adjacent in remaining:
                        remaining.remove(adjacent)
                        group.append(adjacent)
                        stack.append(adjacent)
        degree = Counter(v for e in group for v in e.verts)
        regions.append({
            "id": f"boundary-{len(regions)}", "edge_count": len(group),
            "edge_indices": sorted(e.index for e in group)[:cap],
            "indices_truncated": len(group) > cap,
            "closed_loop": all(n == 2 for n in degree.values()),
            "perimeter_world": sum(e.calc_length() for e in group),
            "intent": "unknown", "automatic_fill_allowed": False,
        })
    return regions


def analyze_mesh(mesh, matrix, config):
    if len(mesh.vertices) > config.max_vertices:
        return {"status": "skipped_limit", "vertices": len(mesh.vertices),
                "reason": "Vertex limit exceeded; isolate a functional component or raise the explicit budget"}
    started = time.monotonic()
    if not all(math.isfinite(n) for row in matrix for n in row):
        return {'status':'invalid_coordinates','reason':'Non-finite transform'}
    local_coordinates = [tuple(float(n) for n in vertex.co) for vertex in mesh.vertices]
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        # Distances, areas, angles and topology are translation invariant.
        # Adding a large world translation to float32 BMesh coordinates can
        # collapse distinct sub-micron vertices and create FALSE degeneracies.
        bm.transform(matrix.to_3x3().to_4x4())
        bm.normal_update()
        for sequence in (bm.verts, bm.edges, bm.faces):
            sequence.ensure_lookup_table()
            sequence.index_update()
        if any(not all(math.isfinite(n) for n in v.co) for v in bm.verts):
            return {"status": "invalid_coordinates", "reason": "Non-finite world coordinates"}
        boundary = [e for e in bm.edges if e.is_boundary]
        wire = [e for e in bm.edges if e.is_wire]
        radial = [e for e in bm.edges if len(e.link_faces) > 2]
        winding = [e for e in bm.edges if e.is_manifold and not e.is_contiguous]
        degenerate = [f for f in bm.faces if f.calc_area() <= config.area_tolerance]
        # Inverted faces: winding order implies a normal opposing bm.faces.normal.
        # Project each face onto the plane perpendicular to the dominant axis of its
        # normal, compute the signed area from the 2D vertex order (shoelace), and
        # compare the implied normal direction with face.normal. A negative dot
        # product (signed_area * normal[dominant_axis] < 0) means the winding
        # opposes the stored normal by more than 90 degrees, so the face is
        # considered inverted.
        inverted_faces = []
        for f in bm.faces:
            normal = f.normal
            ax, ay, az = abs(normal.x), abs(normal.y), abs(normal.z)
            if ax >= ay and ax >= az:
                pts = [(v.co.y, v.co.z) for v in f.verts]
                axis_val = normal.x
            elif ay >= az:
                pts = [(v.co.x, v.co.z) for v in f.verts]
                axis_val = normal.y
            else:
                pts = [(v.co.x, v.co.y) for v in f.verts]
                axis_val = normal.z
            signed_area = 0.0
            n = len(pts)
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                signed_area += x1 * y2 - x2 * y1
            if signed_area * axis_val < 0:
                inverted_faces.append(f)
        # Self-intersection: BVH triangle-triangle overlap, excluding adjacent
        # triangles that share an edge (those are manifold, not intersections).
        self_intersections = []
        try:
            loop_triangles = [tuple(t.vertices) for t in bm.faces[:].loop_triangles] if hasattr(bm.faces[:], 'loop_triangles') else None
        except Exception:
            loop_triangles = None
        if loop_triangles is None:
            bm.calc_loop_triangles()
            loop_triangles = [tuple(t.vertices) for t in bm.loops[:].layers.active_render if False]  # placeholder
            # Rebuild properly:
            tri_list = []
            for f in bm.faces:
                if len(f.verts) == 3:
                    tri_list.append(tuple(v.index for v in f.verts))
                else:
                    # triangulate n-gons using fan from first vertex
                    verts = list(f.verts)
                    for i in range(1, len(verts)-1):
                        tri_list.append((verts[0].index, verts[i].index, verts[i+1].index))
            loop_triangles = tri_list
        points = [v.co for v in bm.verts]
        tree = BVHTree.FromPolygons(points, loop_triangles)
        overlap_pairs = tree.overlap(tree)
        seen = set()
        for pair in overlap_pairs:
            i, j = pair
            if i == j:
                continue
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            seen.add(key)
            # Skip adjacent triangles (share 2 vertices = share an edge)
            tri_i = set(loop_triangles[i])
            tri_j = set(loop_triangles[j])
            if len(tri_i & tri_j) >= 2:
                continue
            self_intersections.append({"triangle_a": i, "triangle_b": j})
            if len(self_intersections) >= config.max_duplicate_pairs:
                break
        zero_edges = [e for e in bm.edges if e.calc_length() <= config.distance_tolerance]
        loose_vertices = [v for v in bm.verts if not v.link_edges]
        nonmanifold_vertices = [v for v in bm.verts if not v.is_manifold]
        tree = KDTree(len(bm.verts))
        for v in bm.verts:
            tree.insert(v.co, v.index)
        tree.balance()
        duplicates = []
        duplicate_cap = False
        for v in bm.verts:
            if time.monotonic() - started > config.max_seconds:
                return {"status": "skipped_time_limit", "reason": "Per-mesh budget exceeded"}
            # KDTree.find_range allocates a list. Hard vertex budget bounds worst case.
            for _, index, distance in tree.find_range(v.co, config.distance_tolerance):
                if index > v.index:
                    duplicates.append({"vertices": [v.index, index], "distance_world": distance})
                    if len(duplicates) >= config.max_duplicate_pairs:
                        duplicate_cap = True
                        break
            if duplicate_cap:
                break
        islands = connected_components(bm.verts)
        shells = []
        for component in islands:
            faces = {f for v in component for f in v.link_faces}
            closed = bool(faces) and all(v.is_manifold for v in component) and all(e.is_manifold for v in component for e in v.link_edges)
            # Evaluate the signed tetrahedra in a nearby LOCAL reference with
            # Python doubles, then apply the affine determinant. World-space
            # float32 cross products caused false negative volumes for small
            # translated screws even when winding/connectivity were correct.
            if closed:
                origin = local_coordinates[component[0].index]
                relative = {v.index: tuple(local_coordinates[v.index][i]-origin[i] for i in range(3)) for v in component}
                def tetra(a,b,c):
                    return (a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
                volume = math.fsum(tetra(relative[f.verts[0].index],relative[f.verts[i].index],relative[f.verts[i+1].index])
                                   for f in faces for i in range(1,len(f.verts)-1))*matrix.to_3x3().determinant()
            else:
                volume = None
            shells.append({"vertices": len(component), "faces": len(faces), "closed": closed,
                           "signed_volume_world": volume,
                           "orientation": "negative_candidate" if volume is not None and volume < 0 else "undetermined"})
        # Containment: check if any shell's centroid is inside another closed shell
        containment = []
        closed_shells = [s for s in shells if s["closed"]]
        for i, s_a in enumerate(closed_shells):
            # Compute centroid of shell A from its component vertices
            comp_a = islands[i]
            centroid_a = tuple(sum(v.co[k] for v in comp_a) / 3 / len(comp_a) for k in range(3))
            from mathutils import Vector
            centroid_a_vec = Vector(centroid_a)
            for j, s_b in enumerate(closed_shells):
                if i == j:
                    continue
                comp_b = islands[j]
                # Test if centroid of A is inside shell B (need world-space matrix)
                # Use the mesh's world matrix for the containment test
                result = point_inside_mesh(mesh, matrix, centroid_a_vec)
                if result == "inside":
                    containment.append({"shell_a": i, "shell_b": j, "result": "contained"})
                    break
                elif result == "unknown":
                    containment.append({"shell_a": i, "shell_b": j, "result": "uncertain"})
        regions = boundary_regions(boundary, config.max_region_indices)
        findings = []

        def finding(kind, elements, severity="warning", confidence=1.0):
            if elements:
                findings.append({"type": kind, "severity": severity, "confidence": confidence,
                                 "count": len(elements), "indices": [e.index for e in elements][:config.max_region_indices],
                                 "indices_truncated": len(elements) > config.max_region_indices,
                                 "safe_to_automate": False, "complexity": "requires_context",
                                 "images": [], "interpretation": "measured_observation"})

        finding("boundary_edges_intent_unknown", boundary)
        finding("radial_nonmanifold_edges", radial, "error")
        finding("nonmanifold_vertices", nonmanifold_vertices)
        finding("inconsistent_winding", winding, "error")
        finding("degenerate_faces", degenerate, "error")
        finding("short_edges", zero_edges)
        finding("loose_edges", wire)
        finding("loose_vertices", loose_vertices)
        finding("inverted_faces", inverted_faces)
        if self_intersections:
            findings.append({"type": "self_intersections", "severity": "error", "confidence": 1.0,
                             "count": len(self_intersections), "pairs": self_intersections,
                             "safe_to_automate": False, "images": [], "complexity": "requires_context",
                             "interpretation": "triangle_overlap_detected"})
        if containment:
            findings.append({"type": "containment", "severity": "warning", "confidence": 0.8,
                             "count": len(containment), "pairs": containment,
                             "safe_to_automate": False, "images": [], "complexity": "requires_context",
                             "interpretation": "shell_inside_shell_detected"})
        if duplicates:
            findings.append({"type": "near_duplicate_vertices", "severity": "warning", "confidence": 1.0,
                             "count": len(duplicates), "count_is_lower_bound": duplicate_cap,
                             "pairs": duplicates, "safe_to_automate": False, "images": [],
                             "complexity": "requires_context", "interpretation": "proximity_not_intent"})
        if any(s["orientation"] == "negative_candidate" for s in shells):
            findings.append({"type": "negative_shell_volume", "severity": "warning", "confidence": 0.7,
                             "safe_to_automate": False, "images": [], "complexity": "requires_context",
                             "interpretation": "May be an intentional inner cavity shell or mirrored transform"})
        planarity, stretch, curvature = [], [], []
        for face in bm.faces:
            if len(face.verts) > 3:
                center = face.calc_center_median()
                planarity.append(max(abs((v.co-center).dot(face.normal)) for v in face.verts))
            lengths = [e.calc_length() for e in face.edges]
            if lengths and min(lengths) > config.distance_tolerance:
                stretch.append(max(lengths) / min(lengths))
        for edge in bm.edges:
            if edge.is_manifold:
                curvature.append(abs(edge.calc_face_angle(0)))
        complete_closed = bool(bm.faces) and not (boundary or wire or radial or nonmanifold_vertices or degenerate or winding)
        return {
            "status": "complete", "fingerprint": mesh_fingerprint(mesh),
            "analysis_matrix": [list(row) for row in matrix],
            "measurement_origin": "translation omitted; linear transform applied in world units",
            "vertices": len(bm.verts), "edges": len(bm.edges), "faces": len(bm.faces),
            "polygon_distribution": dict(Counter(str(len(f.verts)) for f in bm.faces)),
            "edge_length_world": stats(e.calc_length() for e in bm.edges),
            "face_area_world": stats(f.calc_area() for f in bm.faces),
            "planarity_deviation_world": stats(planarity), "edge_ratio": stats(stretch),
            "dihedral_angle_radians": stats(curvature),
            "sharp_edges": sum(not e.smooth for e in bm.edges),
            "normal_summary": {"space": "world", "face_length": stats(f.normal.length for f in bm.faces)},
            "boundary_edge_count": len(boundary), "radial_edge_count": len(radial),
            "nonmanifold_vertex_count": len(nonmanifold_vertices),
            "degenerate_face_count": len(degenerate), "winding_edge_count": len(winding),
            "loose_edge_count": len(wire), "loose_vertex_count": len(loose_vertices),
            "duplicate_pair_count": len(duplicates), "duplicate_count_is_lower_bound": duplicate_cap,
            "island_count": len(islands), "shells": shells, "regions": regions,
            "closed_topology_candidate": complete_closed, "findings": findings,
            "inverted_face_count": len(inverted_faces),
            "inverted_face_indices": sorted(f.index for f in inverted_faces)[:config.max_region_indices],
            "self_intersection_count": len(self_intersections),
            "self_intersection_pairs": self_intersections[:config.max_region_indices],
            "self_intersection_count_is_truncated": len(self_intersections) > config.max_region_indices,
            "containment_count": len(containment),
            "containment_pairs": containment[:config.max_region_indices],
            "coverage": {"self_intersections": "tested", "containment": "tested",
                         "assembly_gaps": "not_tested", "symmetry": "not_inferred",
                         "cylindrical_fit": "not_tested", "manufacturing": "not_certified"},
        }
    finally:
        bm.free()