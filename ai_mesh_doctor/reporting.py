"""Versioned JSON persistence. A failed write never replaces an existing report."""
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    fd, temporary = tempfile.mkstemp(prefix=".doctor-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_report(report):
    if report.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported report schema")
    ids = [obj["id"] for obj in report["objects"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate object IDs")
    for obj in report["objects"]:
        for domain in ("base", "evaluated"):
            geometry = obj.get(domain)
            if not geometry or geometry.get("status") != "complete":
                continue
            for finding in geometry["findings"]:
                if not 0 <= finding["confidence"] <= 1:
                    raise ValueError("Invalid confidence")
                if finding["safe_to_automate"]:
                    raise ValueError("Inspection findings cannot authorize a repair")
    json.dumps(report, allow_nan=False)
    return report
