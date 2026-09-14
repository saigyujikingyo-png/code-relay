"""Exercise the actual stdio process, framing, discovery and tool invocation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from code_relay.contracts import validate_output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="code-relay-mcp-") as temporary:
        config = Path(temporary) / "config.json"
        config.write_text('{"version":1}', encoding="utf-8")
        command = [str(args.exe), "serve"] if args.exe else [sys.executable, "-m", "code_relay", "serve"]
        command += ["--config", str(config), "--state-dir", str(Path(temporary) / "jobs")]
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "synthetic-test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "relay_status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "relay_run", "arguments": {"plan_id": "../escape"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "relay_status", "arguments": {"api_key": "synthetic"}}},
            {"jsonrpc": "2.0", "id": 6, "method": "missing"},
        ]
        result = subprocess.run(command, input="".join(json.dumps(r) + "\n" for r in requests).encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")[:1000]
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(responses) == 6
        assert responses[0]["result"]["protocolVersion"] == "2025-11-25"
        assert len(responses[1]["result"]["tools"]) == 7
        assert all(t["outputSchema"]["type"] == "object" and t["outputSchema"]["anyOf"]
                   for t in responses[1]["result"]["tools"])
        status = responses[2]["result"]
        assert not status["isError"] and not status["structuredContent"]["network_enabled"]
        assert status["structuredContent"]["profiles"] == []
        assert responses[3]["result"]["isError"] and responses[4]["result"]["isError"]
        for tool, response in zip(("relay_status", "relay_run", "relay_status"), responses[2:5]):
            payload = response["result"]
            validate_output(tool, payload["structuredContent"])
            assert json.loads(payload["content"][0]["text"]) == payload["structuredContent"]
        assert responses[5]["error"]["code"] == -32601
        assert result.stderr == b"", result.stderr
        print("PASS: real stdio initialize/list/call, 7 output schemas, validated status/errors and JSON fallback; no API calls.")


if __name__ == "__main__":
    main()
