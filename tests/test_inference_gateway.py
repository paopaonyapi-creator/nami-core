from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from nami_core.app import create_app
from nami_core.inference_gateway import InferenceGateway, InferenceRequest, load_inference_policy


class _ChatHandler(BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        _ChatHandler.received = json.loads(self.rfile.read(length).decode("utf-8"))
        response = {
            "model": _ChatHandler.received.get("model", "test-model"),
            "choices": [{"message": {"content": "hello from gateway"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _server_url() -> tuple[str, ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return f"http://{host}:{port}/v1/chat/completions", server


def _policy_file(tmp_path, backend: str):
    path = tmp_path / "inference_policy.yaml"
    # Tests target a real local HTTP fake (`_ChatHandler`), so we explicitly
    # opt in to the production feature flags that production keeps off by
    # default (Gate 4 rollout). Production policy must remain enabled=false +
    # dry_run=true until the operator flips them; this only relaxes the
    # in-memory test policy.
    path.write_text(
        f"""
enabled: true
dry_run: false
routes:
  - pattern: "test:*"
    backend: "{backend}"
    budget_per_hour:
      tokens: 1000
      cost_usd: 1.0
fallback_order: []
cache:
  enabled: false
""",
        encoding="utf-8",
    )
    return path


def test_inference_gateway_routes_openai_compatible_chat(tmp_path):
    backend, server = _server_url()
    try:
        policy = load_inference_policy(_policy_file(tmp_path, backend))
        gateway = InferenceGateway(policy)
        response = gateway.complete(
            InferenceRequest(
                model="test:gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0,
                max_tokens=64,
            )
        )
    finally:
        server.shutdown()

    assert response.content == "hello from gateway"
    assert response.model_used == "gpt-4o-mini"
    assert response.tokens_in == 12
    assert response.tokens_out == 5
    assert response.cached is False
    assert _ChatHandler.received["model"] == "gpt-4o-mini"
    assert _ChatHandler.received["stream"] is False


def test_runtime_inference_chat_endpoint(tmp_path, monkeypatch):
    backend, server = _server_url()
    policy_path = _policy_file(tmp_path, backend)
    monkeypatch.setenv("NAMI_INFERENCE_POLICY_FILE", str(policy_path))
    try:
        client = TestClient(create_app(api_key="test-key"))
        response = client.post(
            "/runtime/inference/chat",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "test:gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
    finally:
        server.shutdown()

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["content"] == "hello from gateway"
    assert data["tokens_in"] == 12
    assert data["tokens_out"] == 5


def test_runtime_tools_invoke_exposes_nami_llm_chat(tmp_path, monkeypatch):
    backend, server = _server_url()
    policy_path = _policy_file(tmp_path, backend)
    monkeypatch.setenv("NAMI_INFERENCE_POLICY_FILE", str(policy_path))
    try:
        client = TestClient(create_app(api_key="test-key"))
        response = client.post(
            "/runtime/tools/invoke",
            headers={"Authorization": "Bearer test-key"},
            json={"tool": "nami.llm.chat", "payload": {"model": "test:gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}},
        )
    finally:
        server.shutdown()

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["content"] == "hello from gateway"
