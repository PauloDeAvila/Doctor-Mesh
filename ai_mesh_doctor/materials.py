def inspect_materials(obj):
    mesh = obj.data
    return {
        "slots": [{"index": i, "name": slot.material.name_full if slot.material else None,
                   "link": slot.link, "nodes": slot.material.use_nodes if slot.material else False}
                  for i, slot in enumerate(obj.material_slots)],
        "uv_maps": [{"name": layer.name, "active_render": layer.active_render,
                     "loops": len(layer.data)} for layer in mesh.uv_layers],
        "attributes": [{"name": a.name, "domain": a.domain, "data_type": a.data_type} for a in mesh.attributes],
        "custom_normals": mesh.has_custom_normals,
        "shape_keys": [key.name for key in mesh.shape_keys.key_blocks] if mesh.shape_keys else [],
        "uv_distortion": "not_tested", "baking_artifacts": "not_tested",
    }
