"""RNA stack and scene relationship descriptions without evaluating arbitrary code."""
import bpy


def rna_settings(item):
    result = {}
    for prop in item.bl_rna.properties:
        if prop.identifier == "rna_type":
            continue
        try:
            value = getattr(item, prop.identifier)
            if prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
                result[prop.identifier] = list(value) if prop.is_array else value
            elif prop.type == "POINTER" and isinstance(value, bpy.types.ID):
                result[prop.identifier] = {"id_type": value.bl_rna.identifier, "name": value.name_full}
        except (AttributeError, TypeError, ValueError, RuntimeError):
            result[prop.identifier] = "unavailable"
    return result


def inspect_dependencies(obj, ids):
    return {
        "parent_id": ids.get(obj.parent), "children_ids": [ids.get(c) for c in obj.children],
        "instance_type": obj.instance_type,
        "instance_collection": obj.instance_collection.name_full if obj.instance_collection else None,
        "modifiers": [{"name": m.name, "type": m.type, "settings": rna_settings(m)} for m in obj.modifiers],
        "constraints": [{"name": c.name, "type": c.type, "settings": rna_settings(c)} for c in obj.constraints],
        "drivers": [{"path": d.data_path, "index": d.array_index,
                     "targets": [ids.get(t.id) for v in d.driver.variables for t in v.targets if t.id]}
                    for d in obj.animation_data.drivers] if obj.animation_data else [],
        "library": obj.library.filepath if obj.library else None,
    }
