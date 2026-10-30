"""Closed operation vocabulary and strict target/region/fingerprint validation."""
import math

OPERATIONS = {"recalculate_normals", "merge_vertices", "remove_loose", "fit_plane", "smooth_local", "relax_local"}


def validate_plan(plan, report):
    required = {"target_id", "fingerprint", "region", "operation", "parameters", "reason", "constraints"}
    if set(plan) != required or plan["operation"] not in OPERATIONS:
        raise ValueError("Unknown plan fields or operation")
    if type(plan["reason"]) is not str or not plan["reason"].strip():
        raise ValueError("A measured repair justification is required")
    matches = [o for o in report["objects"] if o["id"] == plan["target_id"] and o["type"] == "MESH"]
    if len(matches) != 1:
        raise ValueError("Plan target does not exist")
    geometry = matches[0]["base"]
    if geometry.get("status") != "complete" or geometry["fingerprint"] != plan["fingerprint"]:
        raise ValueError("Plan does not match a complete base mesh scan")
    region = plan["region"]
    if type(region) is not list or not region or len(set(region)) != len(region) or any(type(i) is not int or i < 0 or i >= geometry["vertices"] for i in region):
        raise ValueError("Invalid base vertex region")
    if len(region) > 10000:
        raise ValueError("Region exceeds operation budget")
    params = plan["parameters"]
    if type(params) is not dict:
        raise ValueError("Parameters must be an object")
    allowed = {"recalculate_normals": set(), "merge_vertices": {"distance"}, "remove_loose": set(),
               "fit_plane": {"origin", "normal", "strength"}, "smooth_local": {"strength", "iterations"},
               "relax_local": {"strength", "iterations"}}[plan["operation"]]
    if set(params) != allowed:
        raise ValueError("Operation parameters must match the registry exactly")
    for key in ("origin", "normal"):
        if key in params and (type(params[key]) is not list or len(params[key]) != 3 or any(type(n) not in (int, float) or not math.isfinite(n) for n in params[key])):
            raise ValueError("Invalid vector")
    if "normal" in params and sum(n*n for n in params["normal"]) < 1e-16:
        raise ValueError("Zero plane normal")
    if "strength" in params and (type(params["strength"]) not in (int, float) or not math.isfinite(params["strength"]) or not 0 < params["strength"] <= 1):
        raise ValueError("Invalid correction strength")
    if "iterations" in params and (type(params["iterations"]) is not int or not 1 <= params["iterations"] <= 20):
        raise ValueError("Invalid iteration budget")
    if "distance" in params and (type(params["distance"]) not in (int, float) or not math.isfinite(params["distance"]) or not 0 < params["distance"] <= 0.01):
        raise ValueError("Invalid world distance")
    constraints = plan["constraints"]
    if set(constraints) != {"max_displacement", "max_dimension_delta", "max_topology_delta", "protected_vertices"}:
        raise ValueError("Explicit geometric constraints required")
    for key in ("max_displacement", "max_dimension_delta"):
        if type(constraints[key]) not in (float, int) or not math.isfinite(constraints[key]) or constraints[key] < 0:
            raise ValueError("Invalid constraint")
    if type(constraints["max_topology_delta"]) is not int or not 0 <= constraints["max_topology_delta"] <= 10000:
        raise ValueError("Invalid topology budget")
    if type(constraints["protected_vertices"]) is not list or any(type(i) is not int or not 0 <= i < geometry["vertices"] for i in constraints["protected_vertices"]):
        raise ValueError("Invalid protected region")
    if set(region) & set(constraints["protected_vertices"]):
        raise ValueError("Requested region overlaps protected vertices")
    return matches[0]


def deterministic_plan(record, operation, region, parameters, constraints, reason):
    return {"target_id": record["id"], "fingerprint": record["base"]["fingerprint"],
            "region": region, "operation": operation, "parameters": parameters,
            "constraints": constraints, "reason": reason}
