"""Simplificacao de malha por colapso de aresta (QEM - Quadric Error Metrics).

Reduz a contagem de poligonos preservando a forma visual, essencial para
malhas com topologia limpa e eficiente como produziria um artista 3D.
"""
import math
import bmesh
from mathutils import Vector


def _compute_quadric(v, bm):
    """Matriz quadrica Kp para um vertice, baseada nos planos das faces adjacentes."""
    K = [[0.0] * 4 for _ in range(4)]
    for f in v.link_faces:
        no = f.normal
        # Plano: no.x*x + no.y*y + no.z*z + d = 0
        # d = -no.dot(qualquer_ponto_da_face)
        p = f.verts[0].co
        d = -no.dot(p)
        # K += n * n^T  (4x4 outer product)
        n = [no.x, no.y, no.z, d]
        for i in range(4):
            for j in range(4):
                K[i][j] += n[i] * n[j]
    return K


def _add_quadrics(K1, K2):
    return [[K1[i][j] + K2[i][j] for j in range(4)] for i in range(4)]


def _quadric_error(K, v):
    """Erro quadrico Q(v) = v^T * K * v para vertice v = (x,y,z,1)."""
    x, y, z = v.co.x, v.co.y, v.co.z
    p = [x, y, z, 1.0]
    result = 0.0
    for i in range(4):
        for j in range(4):
            result += p[i] * K[i][j] * p[j]
    return result


def _optimal_vertex(K1, K2, v1, v2):
    """Calcula vertice ideal para o colapso, minimizando erro quadrico."""
    K = _add_quadrics(K1, K2)
    # Resolver sistema K * x = b para minimizar erro
    # Usando o vetor [x,y,z,1] com A = K[0:3][0:3], b = -K[0:3][3]
    A = [[K[i][j] for j in range(3)] for i in range(3)]
    b = [-K[i][3] for i in range(3)]
    # Resolucao 3x3 por eliminacao de Gauss com pivoteamento
    n = 3
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        # Pivoteamento parcial
        max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[max_row][col]) < 1e-12:
            # Matriz singular: usar ponto medio
            return Vector(((v1.co.x + v2.co.x) / 2,
                           (v1.co.y + v2.co.y) / 2,
                           (v1.co.z + v2.co.z) / 2))
        M[col], M[max_row] = M[max_row], M[col]
        for row in range(col + 1, n):
            factor = M[row][col] / M[col][col]
            for k in range(col, n + 1):
                M[row][k] -= factor * M[col][k]
    # Substituicao regressiva
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        for j in range(i + 1, n):
            s -= M[i][j] * x[j]
        if abs(M[i][i]) < 1e-12:
            return Vector(((v1.co.x + v2.co.x) / 2,
                           (v1.co.y + v2.co.y) / 2,
                           (v1.co.z + v2.co.z) / 2))
        x[i] = s / M[i][i]
    return Vector((x[0], x[1], x[2]))


def simplify_edge_collapse(bm, target_ratio=0.5, max_iterations=None,
                           protect_boundary=True, protect_sharp=True):
    """Colapso de aresta iterativo com QEM.

    Colapsa arestas com menor erro quadrico primeiro, ate atingir target_ratio
    da contagem original de faces ou esgotar iteracoes.

    Parametros
    ----------
    bm : bmesh.types.BMesh
    target_ratio : float (0 < ratio <= 1) - proporcao alvo de faces restantes
    max_iterations : int ou None - limite de colapsos (None = ilimitado)
    protect_boundary : bool - nao colapsar arestas de fronteira
    protect_sharp : bool - nao colapsar arestas marcadas como sharp

    Retorna
    -------
    int - numero de colapsos realizados
    """
    if not (0 < target_ratio <= 1):
        raise ValueError("target_ratio deve estar entre 0 e 1")

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    initial_faces = len(bm.faces)
    target_faces = max(4, int(initial_faces * target_ratio))
    if initial_faces <= target_faces:
        return 0

    # Computar quadricas para todos os vertices
    quadrics = {}
    for v in bm.verts:
        quadrics[v.index] = _compute_quadric(v, bm)

    # Calcular custo para cada aresta colapsavel
    edge_costs = {}
    for e in bm.edges:
        if protect_boundary and e.is_boundary:
            continue
        if protect_sharp and e.smooth is False:
            continue
        if len(e.link_faces) == 0:
            continue
        v1, v2 = e.verts
        K = _add_quadrics(quadrics[v1.index], quadrics[v2.index])
        optimal = _optimal_vertex(quadrics[v1.index], quadrics[v2.index], v1, v2)
        error = _quadric_error(K, optimal)
        edge_costs[e.index] = (error, v1.index, v2.index, optimal)

    collapsed = 0
    iterations = 0
    max_iter = max_iterations if max_iterations is not None else len(bm.edges)

    while len(bm.faces) > target_faces and iterations < max_iter and edge_costs:
        iterations += 1
        # Escolher aresta com menor custo
        min_e_idx = min(edge_costs, key=lambda k: edge_costs[k][0])
        error, v1_idx, v2_idx, optimal = edge_costs.pop(min_e_idx)

        e = bm.edges.get(min_e_idx)
        if e is None:
            continue
        v1 = bm.verts.get(v1_idx)
        v2 = bm.verts.get(v2_idx)
        if v1 is None or v2 is None:
            continue

        # Verificar se ainda e colapsavel
        if protect_boundary and e.is_boundary:
            continue
        if protect_sharp and e.smooth is False:
            continue

        # Colapsar: mover v1 para optimal e remover v2
        try:
            v1.co = optimal
            bmesh.ops.remove_doubles(bm, verts=[v1, v2], dist=1e-12)
            # Recalcular quadricas para vertices afetados
            affected = set()
            for edge in v1.link_edges:
                for vert in edge.verts:
                    affected.add(vert.index)
            for vert_idx in affected:
                vert = bm.verts.get(vert_idx)
                if vert is not None:
                    quadrics[vert_idx] = _compute_quadric(vert, bm)
            # Recalcular custos das arestas afetadas
            new_costs = {}
            for edge in bm.edges:
                if protect_boundary and edge.is_boundary:
                    continue
                if protect_sharp and edge.smooth is False:
                    continue
                if len(edge.link_faces) == 0:
                    continue
                a, b = edge.verts
                K = _add_quadrics(quadrics[a.index], quadrics[b.index])
                opt = _optimal_vertex(quadrics[a.index], quadrics[b.index], a, b)
                err = _quadric_error(K, opt)
                new_costs[edge.index] = (err, a.index, b.index, opt)
            edge_costs = new_costs
            collapsed += 1
        except Exception:
            # Se falhar, pular esta aresta
            continue

    return collapsed


def simplify_mesh(mesh, target_ratio=0.5, protect_boundary=True,
                  protect_sharp=True, max_iterations=None):
    """Interface de conveniencia para simplificar um bpy.types.Mesh.

    Retorna o numero de colapsos realizados.
    """
    import bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        n = simplify_edge_collapse(bm, target_ratio=target_ratio,
                                   protect_boundary=protect_boundary,
                                   protect_sharp=protect_sharp,
                                   max_iterations=max_iterations)
        bm.to_mesh(mesh)
        mesh.update()
        return n
    finally:
        bm.free()