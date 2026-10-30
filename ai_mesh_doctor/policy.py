"""Machine-readable construction invariants; no generic hole fill is registered."""
from pathlib import Path
import hashlib

SKILL_NAMES = (
    "blender-mecha-design", "blender-mecha-anatomy", "blender-mecha-optics",
    "blender-mecha-eyes", "blender-mecha-interfaces", "blender-mecha-multiview",
    "blender-local-part-refactor", "blender-dimensional-part-rebuild", "hard-surface",
)

CONSTRUCTION_POLICY = {
    "schema_version": "1.0.0",
    "functional_parts_separate": True,
    "complementary_fragments_rebuild_as_one_part": True,
    "arbitrary_caps_or_patch_objects": False,
    "unclassified_boundaries_block_acceptance": True,
    "require_measured_units_axes_profiles_thickness": True,
    "require_attachment_and_neighbor_constraints": True,
    "require_before_after_horizontal_and_vertical_orbits": True,
    "require_isolated_and_assembled_views": True,
    "require_geometric_and_visual_validation_separately": True,
    "source_inside_same_project": True,
    "successive_blend_backups": False,
    "cleanup_owned_temporary_captures_only_after_explicit_approval": True,
    "reuse_requires_new_measurements_and_validation": True,
}


def skill_manifest(root):
    root = Path(root)
    result = []
    for name in SKILL_NAMES:
        path = root / name / "SKILL.md"
        exists = path.is_file()
        result.append({"name": name, "path": str(path.resolve()), "available": exists,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if exists else None})
    protocol = root / "blender-dimensional-part-rebuild/references/protocolo-integral-360.md"
    if protocol.is_file():
        result.append({"name": "protocolo-integral-360", "path": str(protocol.resolve()), "available": True,
                       "sha256": hashlib.sha256(protocol.read_bytes()).hexdigest()})
    return {"policy": CONSTRUCTION_POLICY, "sources": result,
            "interpretation": "Skills guide decisions; availability does not certify an algorithm"}
