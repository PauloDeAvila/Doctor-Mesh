import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from ai_mesh_doctor.ai_client import DIAGNOSIS_SCHEMA, PROPOSE_REPAIR_TOOL
from ai_mesh_doctor.reporting import atomic_json

atomic_json(root/"schemas/diagnosis.schema.json", DIAGNOSIS_SCHEMA)
atomic_json(root/"schemas/ai-repair-tool.schema.json", PROPOSE_REPAIR_TOOL["parameters"])
schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Mesh Doctor Inspection 1.0.0",
    "type": "object", "required": ["schema_version", "session_id", "status", "units", "objects", "errors", "summary", "coverage"],
    "properties": {
        "schema_version": {"const": "1.0.0"}, "session_id": {"type": "string"},
        "status": {"enum": ["complete", "partial", "cancelled"]},
        "units": {"type": "object", "required": ["metric_space", "scale_length"]},
        "objects": {"type": "array", "items": {"type": "object", "required": ["id", "name", "type", "dependencies"],
            "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "type": {"type": "string"},
                "base": {"$ref": "#/$defs/geometry"}, "evaluated": {"$ref": "#/$defs/geometry"}}}},
        "errors": {"type": "array"}, "summary": {"type": "object"}, "coverage": {"type": "object"}},
    "$defs": {"geometry": {"type": "object", "required": ["status"], "properties": {
        "status": {"enum": ["complete", "skipped_limit", "skipped_time_limit", "invalid_coordinates"]},
        "findings": {"type": "array", "items": {"type": "object", "required": ["type", "confidence", "safe_to_automate"],
            "properties": {"confidence": {"type": "number", "minimum": 0, "maximum": 1}, "safe_to_automate": {"const": False}}}},
        "regions": {"type": "array", "items": {"type": "object", "required": ["id", "automatic_fill_allowed"],
            "properties": {"automatic_fill_allowed": {"const": False}}}}}}}}
atomic_json(root/"schemas/inspection.schema.json", schema)
print("SCHEMAS_EXPORTED")
