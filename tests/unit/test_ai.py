import sys
import json
import unittest
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_mesh_doctor.ai_client import DiagnosticClient, AIConfig, validate_diagnosis
from ai_mesh_doctor.planning import deterministic_plan, validate_plan
from ai_mesh_doctor.reporting import atomic_json

ROOT = Path(__file__).resolve().parents[2]
REPORT = json.loads((ROOT/"examples/inspection.json").read_text(encoding="utf-8"))
TARGET = REPORT["objects"][0]


def ai_config(model="test-only", **kwargs):
    return AIConfig(model, input_usd_per_million=1, output_usd_per_million=2, **kwargs)


def diagnosis():
    return {"stage": "overview", "summary": "No inferred defect", "needs_more_data": False,
            "requested_scans": [], "observations": [{"target_id": TARGET["id"], "region_id": "whole",
            "description": "Measured fixture", "confidence": 1, "evidence": ["scan"]}]}


class FakeSDK:
    def __init__(self, text=None, calls=None, failure=False):
        self.responses = self
        self.input_tokens = self
        self.text = text if text is not None else json.dumps(diagnosis())
        self.calls = calls or []
        self.failure = failure

    def count(self, **kwargs):
        return SimpleNamespace(input_tokens=1000)

    def create(self, **kwargs):
        self.request = kwargs
        if self.failure:
            raise TimeoutError("Simulated provider timeout")
        return SimpleNamespace(status="completed", output=self.calls, output_text=self.text, usage=None)


class AIContract(unittest.TestCase):
    def test_valid_response_and_no_store(self):
        sdk = FakeSDK()
        result = DiagnosticClient(ai_config(allow_network=True), sdk).analyze(REPORT)
        self.assertFalse(result["repairs_executed"])
        self.assertFalse(sdk.request["store"])
        self.assertTrue(sdk.request["text"]["format"]["strict"])

    def test_network_opt_in(self):
        with self.assertRaises(ValueError):
            DiagnosticClient(ai_config(), FakeSDK()).analyze(REPORT)

    def test_unknown_tool_rejected(self):
        call = SimpleNamespace(type="function_call", name="execute_python", arguments="{}")
        with self.assertRaises(ValueError):
            DiagnosticClient(ai_config(allow_network=True), FakeSDK(calls=[call])).analyze(REPORT)

    def test_invented_target_rejected(self):
        data = diagnosis()
        data["observations"][0]["target_id"] = "invented"
        with self.assertRaises(ValueError):
            validate_diagnosis(data, REPORT, "overview")

    def test_additional_scan_request(self):
        call = SimpleNamespace(type="function_call", name="request_additional_scan", arguments=json.dumps({
            "target_id": TARGET["id"], "region_id": "whole", "reason": "Need underside view"}))
        result = DiagnosticClient(ai_config(allow_network=True), FakeSDK(text="", calls=[call])).analyze(REPORT)
        self.assertTrue(result["diagnosis"]["needs_more_data"])

    def test_request_and_payload_budgets(self):
        client = DiagnosticClient(ai_config(allow_network=True), FakeSDK())
        client.analyze(REPORT)
        with self.assertRaises(ValueError):
            client.analyze(REPORT)
        with self.assertRaises(ValueError):
            DiagnosticClient(ai_config(allow_network=True, max_input_bytes=10), FakeSDK()).analyze(REPORT)

    def test_provider_failure_has_no_blender_mutation_path(self):
        with self.assertRaises(TimeoutError):
            DiagnosticClient(ai_config(allow_network=True), FakeSDK(failure=True)).analyze(REPORT)

    def test_cost_budget_denies_expensive_request(self):
        sdk = FakeSDK()
        with self.assertRaises(ValueError):
            DiagnosticClient(ai_config(allow_network=True, max_cost_usd=1e-8), sdk).analyze(REPORT)
        self.assertFalse(hasattr(sdk, "request"))

    def test_model_plan_is_validated_but_never_executed(self):
        args = deterministic_plan(TARGET, "recalculate_normals", [0,1,2],
            {"distance": None, "strength": None, "iterations": None, "origin": None, "normal": None},
            {"max_displacement": 0, "max_dimension_delta": 0, "max_topology_delta": 0, "protected_vertices": []}, "measured fixture")
        call = SimpleNamespace(type="function_call", name="propose_measured_repair", arguments=json.dumps(args))
        result = DiagnosticClient(ai_config(allow_network=True), FakeSDK(text="", calls=[call])).analyze(REPORT)
        self.assertEqual(result["repair_plans"][0]["parameters"], {})
        self.assertFalse(result["repairs_executed"])

    def test_strict_operation_registry_and_stale_fingerprint(self):
        plan = deterministic_plan(TARGET, "recalculate_normals", [0,1,2], {},
            {"max_displacement": 0, "max_dimension_delta": 0, "max_topology_delta": 0, "protected_vertices": []}, "fixture")
        validate_plan(plan, REPORT)
        plan["operation"] = "fill_random_polygon"
        with self.assertRaises(ValueError):
            validate_plan(plan, REPORT)
        plan["operation"] = "recalculate_normals"
        plan["fingerprint"] = "stale"
        with self.assertRaises(ValueError):
            validate_plan(plan, REPORT)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AIContract))
    atomic_json(ROOT/"ai-test-results.json", {"tests": result.testsRun, "success": result.wasSuccessful(),
                "live_api_tested": False, "transport": "injected fake Responses SDK", "failures": len(result.failures), "errors": len(result.errors)})
    if not result.wasSuccessful():
        raise RuntimeError("AI contract tests failed")
