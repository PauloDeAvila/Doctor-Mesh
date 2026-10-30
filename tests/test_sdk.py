"""Actual OpenAI SDK, local mock HTTP transport: no credentials or network."""
import sys
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(Path.home()/"AppData/Roaming/Blender Foundation/Blender/5.4/datafiles/mesh_doctor/python"))
import openai
import httpx2
from ai_mesh_doctor.ai_client import DiagnosticClient, AIConfig
from ai_mesh_doctor.reporting import atomic_json

report = json.loads((root/"examples/inspection.json").read_text(encoding="utf-8"))
diagnosis = {"stage": "overview", "summary": "SDK transport contract verified locally", "needs_more_data": False,
             "requested_scans": [], "observations": []}
calls = []


def handler(request):
    calls.append(request.url.path)
    if request.url.path.endswith("/input_tokens"):
        return httpx2.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
    return httpx2.Response(200, json={"id": "resp_local", "object": "response", "created_at": 1,
        "status": "completed", "model": "local-contract-test", "output": [{"type": "message", "id": "msg_local",
            "status": "completed", "role": "assistant", "content": [{"type": "output_text",
                "text": json.dumps(diagnosis), "annotations": []}]}],
        "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}})


with httpx2.Client(transport=httpx2.MockTransport(handler)) as http:
    client = openai.OpenAI(api_key="local-test-placeholder", base_url="https://mesh-doctor.invalid/v1", http_client=http)
    result = DiagnosticClient(AIConfig("local-contract-test", allow_network=True,
        input_usd_per_million=1, output_usd_per_million=2), client).analyze(report)
assert result["diagnosis"] == diagnosis
assert calls == ["/v1/responses/input_tokens", "/v1/responses"]
atomic_json(root/"sdk-test-results.json", {"success": True, "sdk_version": openai.__version__,
            "python": sys.version, "http_transport": "local MockTransport", "real_network": False, "requests": calls})
print("ACTUAL_SDK_CONTRACT_PASS", openai.__version__)
