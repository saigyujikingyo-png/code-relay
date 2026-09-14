"""Offline end-to-end acceptance with synthetic HTTP providers and disposable source."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

from .common import require
from .core import Relay


class FixtureHandler(BaseHTTPRequestHandler):
    calls = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        request = json.loads(body["messages"][-1]["content"])
        path = request["task"]["write_files"][0]
        text = json.dumps({"summary": "Synthetic candidate.", "files": [{"path": path, "content": "VALUE = 2\n"}]})
        self.calls.append({"path": self.path, "model": body["model"]})
        if self.path == "/v1/messages":
            response = {"id": "synthetic", "type": "message", "role": "assistant",
                        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                        "usage": {"input_tokens": 17, "output_tokens": 23}}
        else:
            response = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
                        "usage": {"prompt_tokens": 17, "completion_tokens": 23}}
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run() -> dict:
    start = time.monotonic()
    captured = []
    handler = type("IsolatedFixture", (FixtureHandler,), {"calls": captured})
    http = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    http.daemon_threads = True
    server = threading.Thread(target=http.serve_forever, daemon=True)
    server.start()
    try:
        with tempfile.TemporaryDirectory(prefix="code-relay-self-test-") as temporary:
            folder = Path(temporary)
            project = folder / "project"
            project.mkdir()
            (project / "fixture.txt").write_text("Synthetic public input.\n", encoding="utf-8")
            profiles = [{"id": protocol, "protocol": protocol, "base_url": f"http://127.0.0.1:{http.server_port}/v1",
                         "model": "synthetic-" + protocol, "key_env": "CODE_RELAY_SELF_TEST_KEY", "allow_loopback_http": True}
                        for protocol in ("openai", "anthropic")]
            config = {"network_enabled": True, "workspaces": [str(project)], "providers": profiles}
            with patch.dict(os.environ, {"CODE_RELAY_SELF_TEST_KEY": "synthetic-offline-only"}):
                relay = Relay(config, state_dir=folder / "state")
                tasks = [{"id": protocol, "instruction": "Create a small numeric fixture.", "kind": "boilerplate",
                          "risk": "low", "complexity": 1, "read_files": ["fixture.txt"],
                          "write_files": [protocol + ".py"], "acceptance": ["VALUE equals 2."],
                          "preferred_provider": protocol} for protocol in ("openai", "anthropic")]
                plan = relay.plan(str(project), tasks)
                relay.run(plan["plan_id"])
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    result = relay.job(plan["plan_id"])
                    if result["state"] not in {"queued", "running"}:
                        break
                    time.sleep(0.02)
                require(result["state"] == "completed", "self_test", "Synthetic provider workflow failed.")
                for protocol in ("openai", "anthropic"):
                    candidate = relay.result(plan["plan_id"], protocol)
                    require("+VALUE = 2" in candidate["diff"] and candidate["source_still_matches"],
                            "self_test", "Candidate or snapshot verification failed.")
                    require(not (project / (protocol + ".py")).exists(), "self_test", "Workspace was unexpectedly modified.")
                relay.run(plan["plan_id"])
                require(len(captured) == 2, "self_test", "Repeated run caused an extra request.")
            return {"status": "passed", "scope": "Synthetic loopback HTTP providers, routing, candidate diffs and idempotency.",
                    "protocols": sorted({c["path"] for c in captured}), "http_requests": len(captured),
                    "workspace_unchanged": True, "elapsed_ms": round((time.monotonic() - start) * 1000),
                    "live_provider_acceptance": "unverified", "model_benchmark": "not_performed"}
    finally:
        http.shutdown()
        http.server_close()
        server.join(timeout=2)
