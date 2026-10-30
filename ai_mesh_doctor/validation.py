"""Independent acceptance gate for measured changes, not aesthetic approval."""
from mathutils import Vector
from .config import InspectionConfig
from .geometry import analyze_mesh


def validate_change(source, candidate, matrix, mapping, region, constraints, operation):
    before = analyze_mesh(source, matrix, InspectionConfig())
    after = analyze_mesh(candidate, matrix, InspectionConfig())
    reasons = []
    if before["status"] != "complete" or after["status"] != "complete":
        return {"accepted": False, "reasons": ["Incomplete geometry inspection"], "before": before, "after": after}
    for key in ("boundary_edge_count", "radial_edge_count", "nonmanifold_vertex_count", "degenerate_face_count", "winding_edge_count"):
        if after[key] > before[key]:
            reasons.append(f"Regressed {key}")
    topology_delta = sum(abs(before[k]-after[k]) for k in ("vertices", "edges", "faces"))
    if topology_delta > constraints["max_topology_delta"]:
        reasons.append("Topology budget exceeded")
    if len(mapping) != len(candidate.vertices) or any(type(i) is not int or not 0 <= i < len(source.vertices) for i in mapping):
        reasons.append("Invalid provenance mapping")
        return {"accepted": False, "reasons": reasons}
    original_world = [matrix @ v.co for v in source.vertices]
    updated_world = [matrix @ v.co for v in candidate.vertices]
    displacement = max(((updated_world[j]-original_world[i]).length for j, i in enumerate(mapping)), default=0)
    if operation == "merge_vertices" and updated_world:
        from mathutils.kdtree import KDTree
        tree = KDTree(len(updated_world))
        for index, coordinate in enumerate(updated_world):
            tree.insert(coordinate, index)
        tree.balance()
        displacement = max(displacement, max((tree.find(original_world[i])[2] for i in region), default=0))
    if displacement > constraints["max_displacement"]+1e-10:
        reasons.append("Displacement budget exceeded")
    reverse = {i: j for j, i in enumerate(mapping)}
    selected = set(region)
    for i, coordinate in enumerate(original_world):
        if i not in selected and (i not in reverse or (updated_world[reverse[i]]-coordinate).length > 1e-10):
            reasons.append("An unaffected/protected vertex changed or disappeared")
            break
    def extent(vertices):
        return Vector([max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in range(3)]) if vertices else Vector()
    dimension_delta = max(abs(n) for n in extent(updated_world)-extent(original_world))
    if dimension_delta > constraints["max_dimension_delta"]+1e-10:
        reasons.append("Dimension budget exceeded")
    metrics = {"recalculate_normals": "winding_edge_count", "merge_vertices": "duplicate_pair_count",
               "remove_loose": "loose_vertex_count"}
    if operation in metrics and after[metrics[operation]] >= before[metrics[operation]]:
        # Fully reversed shells have consistent winding but wrong signed orientation.
        reversed_before = sum(s["orientation"] == "negative_candidate" for s in before["shells"])
        reversed_after = sum(s["orientation"] == "negative_candidate" for s in after["shells"])
        if not (operation == "recalculate_normals" and reversed_after < reversed_before):
            if not (operation == "remove_loose" and after["loose_edge_count"] < before["loose_edge_count"]):
                reasons.append("Target metric did not improve")
    return {"accepted": not reasons, "reasons": reasons, "before": before, "after": after,
            "max_displacement_world": displacement, "max_dimension_delta_world": dimension_delta,
            "topology_delta": topology_delta, "visual_approval": "pending",
            "assembly_validation": "not_tested", "scope": "base mesh only; evaluated modifiers require separate review"}
