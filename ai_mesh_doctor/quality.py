"""Measured quality gates, not a promise of perfect or manufactured geometry."""
from dataclasses import dataclass
import math
import time
import copy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .config import InspectionConfig
from .geometry import analyze_mesh
from .identity import mesh_fingerprint
from .construction_math import through_cut_interval, segments_for_sagitta


@dataclass(frozen=True)
class QualityPolicy:
    coincidence_tolerance: float = 1e-7
    max_triangles: int = 100_000
    max_seconds: float = 20.0
    expected_shells: int = 1

    def __post_init__(self):
        if (not math.isfinite(self.coincidence_tolerance) or self.coincidence_tolerance <= 0
                or not math.isfinite(self.max_seconds) or self.max_seconds <= 0
                or type(self.max_triangles) is not int or self.max_triangles < 1
                or type(self.expected_shells) is not int or self.expected_shells < 1):
            raise ValueError('Invalid quality policy')


def _vector(value, name):
    if len(value) != 3 or not all(math.isfinite(x) for x in value):
        raise ValueError(f'Finite XYZ {name} required')
    return Vector(value)


def check_surface(mesh, matrix, constraint):
    """Explicit measured regions; never select only points already fitting.

    Constraints use world Blender units and indices of the generated mesh.
    A group of triangles is checked against one measured plane/axis.
    """
    indices = constraint['vertices']
    tolerance = constraint['tolerance']
    if (not indices or any(type(i) is not int or not 0 <= i < len(mesh.vertices) for i in indices)
            or not math.isfinite(tolerance) or tolerance <= 0):
        raise ValueError('Valid region indices and positive measured tolerance required')
    origin = _vector(constraint['origin'], 'origin')
    normal = _vector(constraint['normal'], 'normal')
    if normal.length < 1e-12:
        raise ValueError('Measured axis is zero')
    normal.normalize()
    # Preserve precision: subtract translation before transforming local points.
    offset = matrix.translation-origin
    linear = matrix.to_3x3()
    points = [linear @ mesh.vertices[i].co + offset for i in indices]
    axial = [p.dot(normal) for p in points]
    family = constraint['family']
    if family == 'plane':
        errors = [abs(x) for x in axial]
    elif family in ('circle', 'cylinder'):
        radius = constraint['radius']
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError('Positive measured radius required')
        errors = [abs((p-normal*z).length-radius) for p,z in zip(points,axial)]
        if family == 'circle':
            errors = [max(error,abs(z)) for error,z in zip(errors,axial)]
    else:
        raise ValueError('Unsupported measured surface family')
    return {'family': family, 'vertices': len(indices), 'tolerance': tolerance,
            'max_error': max(errors), 'rms_error': math.sqrt(sum(x*x for x in errors)/len(errors)),
            'accepted': max(errors) <= tolerance}


def _triangles(mesh, matrix, origin=None):
    mesh.calc_loop_triangles()
    linear = matrix.to_3x3()
    offset = matrix.translation - (origin if origin is not None else matrix.translation)
    points = [linear @ v.co + offset for v in mesh.vertices]
    triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
    normals = [(points[b]-points[a]).cross(points[c]-points[a]).normalized() for a,b,c in triangles]
    tree = BVHTree.FromPolygons(points, triangles, all_triangles=True)
    return points, triangles, normals, tree


def _coincident(a, b, policy, started, same_mesh=False, contact=None):
    points, triangles, normals, _ = a
    _, other_triangles, other_normals, tree = b
    examples = []
    for i, triangle in enumerate(triangles):
        if time.monotonic()-started > policy.max_seconds:
            return {'status': 'budget_exceeded', 'examples': examples}
        center = sum((points[k] for k in triangle), Vector()) / 3
        for location, _, j, distance in tree.find_nearest_range(center, policy.coincidence_tolerance):
            if same_mesh and (j <= i or set(triangle) & set(other_triangles[j])):
                continue
            dot = normals[i].dot(other_normals[j])
            if abs(dot) < .9999:
                continue
            # Opposed faces may be a declared planar mating contact. Shared
            # same-facing bore walls are NOT explained away by this declaration.
            intentional = False
            if contact and dot < 0:
                n = _vector(contact['normal'], 'contact normal').normalized()
                intentional = (abs((center-_vector(contact['origin'], 'contact origin')).dot(n)) <= contact['tolerance']
                               and abs(normals[i].dot(n)) > .9999)
            if not intentional:
                examples.append({'triangle_a': i, 'triangle_b': j, 'distance': distance,
                                 'orientation': 'same_facing' if dot > 0 else 'opposed'})
                if len(examples) >= 16:
                    return {'status': 'defect_found', 'examples': examples}
    return {'status': 'defect_found' if examples else 'complete', 'examples': examples}


def audit_mesh(mesh, matrix, constraints=(), policy=None, geometry_report=None):
    policy = policy or QualityPolicy()
    started = time.monotonic()
    signature = mesh_fingerprint(mesh)
    matrix_values = [list(row) for row in matrix]
    if (geometry_report is None or geometry_report.get('fingerprint') != signature
            or geometry_report.get('analysis_matrix') != matrix_values):
        geometry_report = analyze_mesh(mesh, matrix, InspectionConfig(
            distance_tolerance=policy.coincidence_tolerance,
            area_tolerance=policy.coincidence_tolerance**2,
            max_seconds=policy.max_seconds))
    reasons = []
    if geometry_report.get('status') != 'complete':
        reasons.append('geometry_incomplete')
    else:
        for field in ('boundary_edge_count','radial_edge_count','nonmanifold_vertex_count',
                      'degenerate_face_count','winding_edge_count','loose_vertex_count',
                      'loose_edge_count','duplicate_pair_count'):
            if geometry_report.get(field):
                reasons.append(field)
        if geometry_report['island_count'] != policy.expected_shells:
            reasons.append('unexpected_shell_count')
        if any(not s['closed'] or (s['signed_volume_world'] or 0) <= 0 for s in geometry_report['shells']):
            reasons.append('nonpositive_or_open_shell')
    surfaces = [check_surface(mesh,matrix,c) for c in constraints]
    if any(not s['accepted'] for s in surfaces):
        reasons.append('measured_surface_error')
    coincidence = {'status': 'not_run'}
    if not reasons:
        mesh.calc_loop_triangles()
        if len(mesh.loop_triangles) > policy.max_triangles:
            coincidence = {'status': 'budget_exceeded'}
        else:
            data = _triangles(mesh,matrix)
            coincidence = _coincident(data,data,policy,started,same_mesh=True)
        if coincidence['status'] != 'complete':
            reasons.append('coincident_faces_or_incomplete_check')
    return {'accepted': not reasons, 'reasons': reasons, 'fingerprint': signature,
            'analysis_matrix': matrix_values, 'geometry': copy.deepcopy(geometry_report),
            'surfaces': surfaces, 'coincident_faces': coincidence,
            'elapsed_seconds': time.monotonic()-started, 'visual_approval': 'pending',
            'coverage': {'general_self_intersections': 'not_tested', 'wall_thickness': 'not_tested',
                         'assembly': 'separate_interface_check_required', 'manufacturing': 'not_certified'}}


def audit_component(obj, constraints=(), policy=None):
    return audit_mesh(obj.data,obj.matrix_world,constraints,policy)


def inspect_coincident_interface(a, b, contact=None, policy=None):
    policy = policy or QualityPolicy()
    started = time.monotonic()
    a.data.calc_loop_triangles();b.data.calc_loop_triangles()
    if len(a.data.loop_triangles)+len(b.data.loop_triangles) > policy.max_triangles:
        return {'accepted': False, 'status': 'budget_exceeded'}
    origin = a.matrix_world.translation
    # Contact plane is expressed in this common translated frame, just as BVH.
    local_contact = None if contact is None else dict(contact)
    if local_contact is not None:
        local_contact['origin'] = list(_vector(contact['origin'],'contact origin')-origin)
        if not math.isfinite(contact['tolerance']) or contact['tolerance'] <= 0:
            raise ValueError('Positive contact tolerance required')
    aa, bb = _triangles(a.data,a.matrix_world,origin), _triangles(b.data,b.matrix_world,origin)
    forward = _coincident(aa,bb,policy,started,contact=local_contact)
    reverse = _coincident(bb,aa,policy,started,contact=local_contact)
    return {'accepted': forward['status'] == reverse['status'] == 'complete',
            'forward': forward, 'reverse': reverse,
            'coverage': 'centroid-based near-coplanar overlap screening; general crossing/containment not certified'}
