"""Subdivisao Loop para malhas triangulares.

Produz superfícies suaves e organicas como um artista 3D alcançaria
com modificador Subdivision Surface, mas com controle deterministico.
"""
import bmesh
from mathutils import Vector


def subdivide_loop(bm, iterations=1, protect_boundary=True):
    """Subdivisao Loop iterativa.

    Cada iteracao divide cada triangulo em 4 subtriangulos e reposiciona
    vertices usando mascaras de Loop (media ponderada de vizinhos).

    Parametros
    ----------
    bm : bmesh.types.BMesh (deve conter apenas triângulos)
    iterations : int (>= 1)
    protect_boundary : bool - manter vertices de fronteira na posicao original

    Retorna
    -------
    int - numero de faces apos a subdivisao
    """
    if iterations < 1:
        raise ValueError("iterations deve ser >= 1")

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Garantir que todas as faces são triângulos
    for f in list(bm.faces):
        if len(f.verts) != 3:
            raise ValueError("Subdivisao Loop requer malha totalmente triangular")

    for _ in range(iterations):
        _subdivide_loop_once(bm, protect_boundary)

    bm.normal_update()
    return len(bm.faces)


def _subdivide_loop_once(bm, protect_boundary):
    """Uma iteracao de subdivisao Loop."""
    old_verts = list(bm.verts)
    old_faces = list(bm.faces)
    old_edges = list(bm.edges)

    # Marcar vertices antigos
    old_layer = bm.verts.layers.int.new("_md_old")
    for v in old_verts:
        v[old_layer] = 1

    # 1. Criar novos vertices no ponto medio de cada aresta
    edge_midpoints = {}
    for e in old_edges:
        if protect_boundary and e.is_boundary:
            continue
        v1, v2 = e.verts
        mid = (v1.co + v2.co) / 2.0
        new_v = bm.verts.new(mid)
        new_v[old_layer] = 0
        edge_midpoints[e.index] = new_v

    # 2. Reposicionar vertices antigos com mascara de Loop
    for v in old_verts:
        if protect_boundary and v.is_boundary:
            continue
        neighbor_verts = [e.other_vert(v) for e in v.link_edges]
        n = len(neighbor_verts)
        if n == 0:
            continue
        if n == 3:
            beta = 3.0 / 16.0
        else:
            beta = 3.0 / (8.0 * n)
        avg_neighbor = sum((nv.co for nv in neighbor_verts), Vector()) / n
        v.co = (1.0 - n * beta) * v.co + beta * avg_neighbor

    # 3. Reconstruir faces: cada triângulo antigo vira 4 novos
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    new_faces = []
    for f in old_faces:
        v1, v2, v3 = f.verts
        e12 = _find_edge(bm, v1, v2)
        e23 = _find_edge(bm, v2, v3)
        e31 = _find_edge(bm, v3, v1)
        m12 = edge_midpoints.get(e12.index) if e12 else None
        m23 = edge_midpoints.get(e23.index) if e23 else None
        m31 = edge_midpoints.get(e31.index) if e31 else None

        if m12 and m23 and m31:
            # 4 subtriangulos
            try:
                new_faces.append(bm.faces.new((v1, m12, m31)))
                new_faces.append(bm.faces.new((m12, v2, m23)))
                new_faces.append(bm.faces.new((m31, m23, v3)))
                new_faces.append(bm.faces.new((m12, m23, m31)))
            except Exception:
                pass

    # Deletar faces antigas
    if old_faces:
        bmesh.ops.delete(bm, geom=old_faces, context="FACES")

    bm.verts.layers.int.remove(old_layer)
    bm.normal_update()


def _find_edge(bm, v1, v2):
    """Encontra aresta entre dois vertices."""
    for e in v1.link_edges:
        if e.other_vert(v1) == v2:
            return e
    return None


def subdivide_mesh(mesh, iterations=1, protect_boundary=True):
    """Interface de conveniencia para subdividir um bpy.types.Mesh."""
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        n = subdivide_loop(bm, iterations=iterations,
                           protect_boundary=protect_boundary)
        bm.to_mesh(mesh)
        mesh.update()
        return n
    finally:
        bm.free()