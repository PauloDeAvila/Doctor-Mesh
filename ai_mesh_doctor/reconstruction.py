"""Complete functional solids from measured simple profiles; no boundary patch fill.

An extruded profile defines the entire volume. A revolved closed (r,z) profile
defines both outer and inner walls; an annular bore is an intentional void,
not an open topological boundary. Unknown freeform shapes are unsupported.
"""
import math
from uuid import uuid4
import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon
from mathutils.bvhtree import BVHTree
from .config import InspectionConfig
from .geometry import analyze_mesh
from .repair import state_signature


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def validate_profile(profile):
    if type(profile) is not list or not 3 <= len(profile) <= 256:
        raise ValueError("A complete ordered profile with 3..256 points is required")
    if any(type(p) is not list or len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in profile):
        raise ValueError("Profile coordinates must be finite numbers")
    scale = max(max(abs(n) for n in p) for p in profile)
    epsilon = max(1e-14, scale*scale*1e-12)
    n = len(profile)
    for i in range(n):
        a, b = profile[i], profile[(i+1)%n]
        if sum((x-y)**2 for x,y in zip(a,b)) <= epsilon:
            raise ValueError("Duplicate/zero length profile edge")
        for j in range(i+1, n):
            if j == i+1 or (i == 0 and j == n-1):
                continue
            c, d = profile[j], profile[(j+1)%n]
            # Includes touches and collinear overlaps, rejected conservatively.
            ab_c, ab_d, cd_a, cd_b = _cross(a,b,c), _cross(a,b,d), _cross(c,d,a), _cross(c,d,b)
            boxes_overlap = all(max(min(a[k],b[k]), min(c[k],d[k])) <= min(max(a[k],b[k]), max(c[k],d[k]))+math.sqrt(epsilon) for k in range(2))
            if boxes_overlap and ab_c*ab_d <= epsilon**2 and cd_a*cd_b <= epsilon**2:
                raise ValueError("Self-intersecting or touching profile is unsupported")
    area = sum(profile[i][0]*profile[(i+1)%n][1]-profile[(i+1)%n][0]*profile[i][1] for i in range(n))/2
    if abs(area) <= epsilon:
        raise ValueError("Profile has no measurable area")
    return profile if area > 0 else list(reversed(profile))


def validate_spec(spec):
    required = {"family", "profile", "depth", "segments", "frame", "units", "measurement_evidence",
                "expected_bounds_local", "tolerance", "intentional_voids", "attachment_points", "neighbor_constraints"}
    if set(spec) != required or spec["family"] not in {"extruded_profile", "revolved_profile"}:
        raise ValueError("Unsupported reconstruction family or fields")
    profile = validate_profile(spec["profile"])
    if not spec["units"] or not spec["measurement_evidence"]:
        raise ValueError("Units and measurement sources are mandatory")
    if type(spec["tolerance"]) not in (float, int) or not math.isfinite(spec["tolerance"]) or not 0 < spec["tolerance"] <= 0.01:
        raise ValueError("Measured tolerance must be positive and <= 0.01 world units")
    if type(spec["depth"]) not in (int, float) or not math.isfinite(spec["depth"]) or spec["depth"] <= 0:
        raise ValueError("Positive depth is required")
    if type(spec["segments"]) is not int or not 16 <= spec["segments"] <= 512:
        raise ValueError("Segment budget must be 16..512")
    if spec["family"] == "revolved_profile" and min(p[0] for p in profile) <= 0:
        raise ValueError("Revolved profile must stay strictly outside the axis; use a measured inner wall")
    frame = spec["frame"]
    if type(frame) is not list or len(frame) != 4 or any(type(row) is not list or len(row) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in row) for row in frame):
        raise ValueError("Frame must be a finite 4x4 matrix")
    matrix = Matrix(frame)
    rotation = matrix.to_3x3()
    if max(abs(rotation.col[i].dot(rotation.col[j])-(1 if i == j else 0)) for i in range(3) for j in range(3)) > 1e-5 or abs(rotation.determinant()-1) > 1e-5 or max(abs(matrix[3][i]-(1 if i == 3 else 0)) for i in range(4)) > 1e-6:
        raise ValueError("Measured frame must be rigid and right handed; incorporate scale into dimensions")
    bounds = spec["expected_bounds_local"]
    if type(bounds) is not list or len(bounds) != 3 or any(type(row) is not list or len(row) != 2 or any(type(v) not in (float, int) or not math.isfinite(v) for v in row) or row[0] >= row[1] for row in bounds):
        raise ValueError("Independent expected bounds are required")
    if type(spec["attachment_points"]) is not list or type(spec["neighbor_constraints"]) is not dict:
        raise ValueError("Attachment/neighbor specifications required")
    return profile, matrix


def build_component(spec, name="MeasuredComponent"):
    profile, frame = validate_spec(spec)
    vertices, faces = [], []
    if spec["family"] == "extruded_profile":
        n = len(profile)
        vertices = [(x,y,z) for z in (-spec["depth"]/2, spec["depth"]/2) for x,y in profile]
        polygon = [Vector((x,y,0)) for x,y in profile]
        index = {(v.x,v.y): i for i,v in enumerate(polygon)}
        for triangle in tessellate_polygon([polygon]):
            # Blender 5.4 returns indices; older supported versions returned vectors.
            indices = [v if isinstance(v, int) else index[(v.x,v.y)] for v in triangle]
            faces.append(tuple(reversed(indices)))
            faces.append(tuple(i+n for i in indices))
        faces.extend((i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n))
    else:
        count, n = spec["segments"], len(profile)
        vertices = [(r*math.cos(2*math.pi*j/count), r*math.sin(2*math.pi*j/count), z)
                    for r,z in profile for j in range(count)]
        for i in range(n):
            for j in range(count):
                faces.append((i*count+j, i*count+(j+1)%count,
                              ((i+1)%n)*count+(j+1)%count, ((i+1)%n)*count+j))
    mesh = bpy.data.meshes.new(name)
    try:
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        import bmesh
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(mesh)
        finally:
            bm.free()
        report = analyze_mesh(mesh, frame, InspectionConfig())
        if not report["closed_topology_candidate"] or report["duplicate_pair_count"] or report["island_count"] != 1 or report["shells"][0]["signed_volume_world"] <= 0:
            raise ValueError("Generated component failed closed-solid topology validation")
        bounds = [[min(v.co[i] for v in mesh.vertices), max(v.co[i] for v in mesh.vertices)] for i in range(3)]
        error = max(abs(bounds[i][j]-spec["expected_bounds_local"][i][j]) for i in range(3) for j in range(2))
        if error > spec["tolerance"]:
            raise ValueError("Generated dimensions differ from independent measured bounds")
        # Semantic regions come from construction indices, never from selecting
        # whichever candidate vertices happen to fit a requested surface.
        from .quality import audit_mesh
        constraints = []
        if spec['family'] == 'extruded_profile':
            for layer,z in enumerate((-spec['depth']/2,spec['depth']/2)):
                constraints.append({'family':'plane','vertices':list(range(layer*len(profile),(layer+1)*len(profile))),
                    'origin':list(frame @ Vector((0,0,z))),
                    'normal':list(frame.to_3x3() @ Vector((0,0,1))), 'tolerance':spec['tolerance']})
        else:
            for index,(radius,z) in enumerate(profile):
                constraints.append({'family':'circle','vertices':list(range(index*spec['segments'],(index+1)*spec['segments'])),
                    'origin':list(frame @ Vector((0,0,z))),
                    'normal':list(frame.to_3x3() @ Vector((0,0,1))),
                    'radius':radius,'tolerance':spec['tolerance']})
        quality = audit_mesh(mesh,frame,constraints,geometry_report=report)
        if not quality['accepted']:
            raise ValueError('Measured quality gate rejected component: '+', '.join(quality['reasons']))
        report['quality_gate'] = quality
        bvh = BVHTree.FromPolygons([v.co for v in mesh.vertices], [p.vertices[:] for p in mesh.polygons])
        for point in spec["attachment_points"]:
            if type(point) is not list or len(point) != 3:
                raise ValueError("Attachment point must be a measured local XYZ coordinate")
            nearest = bvh.find_nearest(Vector(point))
            if nearest[0] is None or nearest[3] > spec["tolerance"]:
                raise ValueError("Attachment point does not meet reconstructed surface")
        obj = bpy.data.objects.new(name, mesh)
        obj.matrix_world = frame
        obj["mesh_doctor_component"] = str(uuid4())
        report.update(measured_bounds_local=bounds, max_bounds_error=error,
                      intentional_voids=spec["intentional_voids"], attachment_points_checked=len(spec["attachment_points"]),
                      visual_approval="pending", reference_similarity="not_scored")
        return obj, report
    except Exception:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def _tree(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return BVHTree.FromPolygons([evaluated.matrix_world @ v.co for v in mesh.vertices],
                                   [p.vertices[:] for p in mesh.polygons]), [evaluated.matrix_world @ v.co for v in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def _inside(tree, point, epsilon):
    votes = []
    for direction in (Vector((1,0.371,0.217)).normalized(), Vector((0.173,1,0.419)).normalized(), Vector((0.319,0.127,1)).normalized()):
        count, origin = 0, point.copy()
        for _ in range(2048):
            location, _, _, _ = tree.ray_cast(origin, direction)
            if location is None:
                break
            count += 1
            origin = location+direction*epsilon
        else:
            return "unknown"
        votes.append(count % 2 == 1)
    return "inside" if all(votes) else "outside" if not any(votes) else "unknown"


def inspect_neighbors(context, candidate, source, spec):
    """Broad AABB rejection + triangle overlap + containment samples.

    Disjoint AABBs prove separation. Others remain unresolved unless overlap or
    containment is measured. This deliberately does not certify minimum clearance.
    """
    context.view_layer.update()
    graph = context.evaluated_depsgraph_get()
    target_tree, target_points = _tree(candidate, graph)
    pairs = []
    for obj in context.scene.objects:
        if obj in (candidate, source) or obj.type != "MESH" or obj.get("mesh_doctor_transaction"):
            continue
        points = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
        separate = any(max(v[i] for v in target_points) < min(v[i] for v in points)-spec["tolerance"] or
                       max(v[i] for v in points) < min(v[i] for v in target_points)-spec["tolerance"] for i in range(3))
        if separate:
            pairs.append({"neighbor": obj.name_full, "result": "separated_aabb", "classification": "clear"})
            continue
        tree, neighbor_points = _tree(obj, graph)
        overlap = bool(target_tree.overlap(tree))
        # Surface sample in both directions detects common closed containment cases.
        contained = _inside(tree, target_points[0], spec["tolerance"]*0.1) if target_points else "unknown"
        contains = _inside(target_tree, neighbor_points[0], spec["tolerance"]*0.1) if neighbor_points else "unknown"
        result = "surface_overlap" if overlap else "containment_candidate" if "inside" in (contained, contains) else "unresolved_proximity"
        classification = spec["neighbor_constraints"].get(obj.name_full, "unclassified")
        if classification not in {"intentional_contact", "intentional_overlap", "clearance_reviewed", "unclassified"}:
            raise ValueError("Invalid neighbor interpretation")
        pairs.append({"neighbor": obj.name_full, "result": result, "classification": classification,
                      "inside_samples": [contained, contains], "exact_clearance": "not_measured"})
    return {"pairs": pairs, "unclassified": sum(p["classification"] == "unclassified" for p in pairs),
            "limitations": "Sampled containment assumes closed neighbors; exact minimum clearance and swept motion are not certified"}
