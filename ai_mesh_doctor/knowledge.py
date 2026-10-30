"""Local evidence store: explicit recipes, test evidence and approval are separate.

This is retrieval, not model training. Recipes are candidates and never executable text.
"""
import json
import sqlite3
import math
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from .reporting import utc_now


class KnowledgeStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, family TEXT NOT NULL,
                technical_status TEXT NOT NULL, approval TEXT NOT NULL, payload TEXT NOT NULL)""")

    def record(self, case):
        required = {"project", "scope", "family", "units", "measurements", "method", "parameters",
                    "problems", "corrections", "evidence", "tests", "limitations", "sources",
                    "technical_status", "approval", "reusable_rule", "valid_ranges"}
        if not required <= case.keys():
            raise ValueError(f"Missing case fields: {sorted(required-case.keys())}")
        if case["technical_status"] not in {"documented", "tested", "rejected"}:
            raise ValueError("Invalid technical status")
        if case["approval"] not in {"pending", "approved", "rejected"}:
            raise ValueError("Invalid approval status")
        if case["technical_status"] == "tested" and (not case["tests"] or not case["evidence"]):
            raise ValueError("Tested cases require tests and evidence")
        for key, interval in case["valid_ranges"].items():
            if len(interval) != 2 or not all(type(n) in (float, int) and math.isfinite(n) for n in interval) or interval[0] > interval[1]:
                raise ValueError(f"Invalid range: {key}")
        # A new revision is an immutable entry, preserving rejected approaches.
        identifier = str(uuid4())
        payload = json.dumps(case, ensure_ascii=False, allow_nan=False)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?)",
                       (identifier, utc_now(), case["family"], case["technical_status"], case["approval"], payload))
        return identifier

    def candidates(self, family, units, parameters):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT id,payload FROM cases WHERE family=? AND technical_status='tested' AND approval='approved'", (family,)).fetchall()
        results = []
        for identifier, payload in rows:
            case = json.loads(payload)
            ranges = case["valid_ranges"]
            if case["units"] != units or not ranges or not ranges.keys() <= parameters.keys():
                continue
            if all(type(parameters[k]) in (int, float) and math.isfinite(parameters[k]) and lo <= parameters[k] <= hi
                   for k, (lo, hi) in ranges.items()):
                results.append({"id": identifier, "case": case, "requires_new_validation": True})
        return results
