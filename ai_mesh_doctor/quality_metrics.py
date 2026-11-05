"""Metricas de qualidade puras — sem dependencia do Blender.

Funcaoes que operam sobre coordenadas vetoriais e topologia de triangulos,
permitindo teste unitario sem necessidade de bpy/bmesh.
"""
import math
from mathutils import Vector


def element_quality_metrics(points, triangles, normals):
    """Metricas de qualidade por triangulo.

    Parametros
    ----------
    points : sequence de mathutils.Vector
        Coordenadas dos vertices.
    triangles : sequence de 3-tuplas de int
        Indices dos vertices de cada triangulo.
    normals : sequence de mathutils.Vector
        Normais das faces (mantida para consistencia da interface).

    Retorna
    -------
    dict com listas: aspect_ratio, skewness, jacobian, internal_angles
    """
    aspect_ratios = []
    skewnesses = []
    jacobians = []
    internal_angles_list = []

    def angle(u, v):
        lu = u.length
        lv = v.length
        if lu <= 0 or lv <= 0:
            return 0.0
        dot = max(-1.0, min(1.0, u.dot(v) / (lu * lv)))
        return math.degrees(math.acos(dot))

    for triangle in triangles:
        a, b, c = (points[i] for i in triangle)
        e1 = b - a
        e2 = c - a
        e3 = c - b
        l1 = e1.length
        l2 = e2.length
        l3 = e3.length
        min_edge = min(l1, l2, l3)
        max_edge = max(l1, l2, l3)
        aspect_ratio = (max_edge / min_edge) if min_edge > 0 else float('inf')

        ang_a = angle(b - a, c - a)
        ang_b = angle(a - b, c - b)
        ang_c = angle(a - c, b - c)
        angles = [ang_a, ang_b, ang_c]
        skewness = max(abs(ang - 60.0) for ang in angles)

        area = e1.cross(e2).length / 2.0
        jacobian = (2.0 * area) / (l1 * l2) if (l1 > 0 and l2 > 0) else 0.0

        aspect_ratios.append(aspect_ratio)
        skewnesses.append(skewness)
        jacobians.append(jacobian)
        internal_angles_list.append(angles)

    return {
        'aspect_ratio': aspect_ratios,
        'skewness': skewnesses,
        'jacobian': jacobians,
        'internal_angles': internal_angles_list,
    }


def detect_inverted_faces(points, triangles, normals):
    """Indices de faces cujo winding se opõe à normal.

    Uma face e' considerada invertida quando a normal calculada pela ordem
    dos vertices se opõe à normal armazenada (produto escalar < 0).

    Retorna
    -------
    lista de int: indices das faces invertidas
    """
    inverted = []
    for i, triangle in enumerate(triangles):
        a, b, c = (points[j] for j in triangle)
        computed = (b - a).cross(c - a)
        if computed.length < 1e-12:
            continue
        computed.normalize()
        normal = normals[i]
        if computed.dot(normal) < 0:
            inverted.append(i)
            continue
        # Area assinada 2D da projecao no plano perpendicular à normal
        comps = [abs(normal.x), abs(normal.y), abs(normal.z)]
        drop = comps.index(max(comps))
        keep = [j for j in range(3) if j != drop]
        p = [(points[j][keep[0]], points[j][keep[1]]) for j in triangle]
        (x1, y1), (x2, y2), (x3, y3) = p
        signed_area = 0.5 * ((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
        if signed_area < 0:
            inverted.append(i)
    return inverted


def validate_perfect_mesh(geometry_report, policy=None):
    """Valida se uma malha atinge qualidade de artista 3D profissional.

    Verifica que a malha e': watertight, sem auto-intersecao, sem faces
    degeneradas, sem normais invertidas, sem nao-manifold, sem vertices
    soltos, topologia fechada e com qualidade de elemento adequada.

    Parametros
    ----------
    geometry_report : dict
        Resultado de analyze_mesh() ou audit_mesh()['geometry'].
    policy : QualityPolicy ou None
        Thresholds opcionais para qualidade de elemento.

    Retorna
    -------
    dict : {'perfect': bool, 'reasons': list[str], 'score': float (0-1)}
    """
    from .quality import QualityPolicy
    policy = policy or QualityPolicy()
    reasons = []
    score = 1.0

    if geometry_report.get('status') != 'complete':
        return {'perfect': False, 'reasons': ['geometry_incomplete'], 'score': 0.0}

    # Topologia: sem nao-manifold, sem faces degeneradas, sem winding inconsistente
    if geometry_report.get('radial_edge_count', 0) > 0:
        reasons.append('radial_nonmanifold_edges')
        score -= 0.2
    if geometry_report.get('nonmanifold_vertex_count', 0) > 0:
        reasons.append('nonmanifold_vertices')
        score -= 0.2
    if geometry_report.get('degenerate_face_count', 0) > 0:
        reasons.append('degenerate_faces')
        score -= 0.15
    if geometry_report.get('winding_edge_count', 0) > 0:
        reasons.append('inconsistent_winding')
        score -= 0.15

    # Sem geometria solta ou duplicada
    if geometry_report.get('loose_vertex_count', 0) > 0:
        reasons.append('loose_vertices')
        score -= 0.1
    if geometry_report.get('loose_edge_count', 0) > 0:
        reasons.append('loose_edges')
        score -= 0.1
    if geometry_report.get('duplicate_pair_count', 0) > 0:
        reasons.append('near_duplicate_vertices')
        score -= 0.1

    # Sem auto-intersecao ou contencao problematica
    if geometry_report.get('self_intersection_count', 0) > 0:
        reasons.append('self_intersections')
        score -= 0.25
    if geometry_report.get('containment_count', 0) > 0:
        reasons.append('containment_detected')
        score -= 0.15

    # Sem faces invertidas
    if geometry_report.get('inverted_face_count', 0) > 0:
        reasons.append('inverted_faces')
        score -= 0.2

    # Topologia fechada e sem bordas abertas (a menos que intencional)
    if geometry_report.get('boundary_edge_count', 0) > 0:
        reasons.append('boundary_edges_open')
        score -= 0.1

    if not geometry_report.get('closed_topology_candidate', False):
        reasons.append('topology_not_closed')
        score -= 0.15

    # Volume positivo para cascas fechadas
    for s in geometry_report.get('shells', []):
        if s.get('closed') and (s.get('signed_volume_world') or 0) <= 0:
            reasons.append('nonpositive_or_open_shell')
            score -= 0.2
            break

    score = max(0.0, min(1.0, score))
    perfect = len(reasons) == 0

    return {'perfect': perfect, 'reasons': reasons, 'score': score}