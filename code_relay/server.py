"""A small MCP stdio adapter; all coding policy lives in the shared core."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .common import RelayError, digest, json_bytes, require, strict_json
from .config import config_path, load_config
from .contracts import CONTRACT_VERSION, OUTPUT_SCHEMAS, error_output, validate_output
from .core import Relay
from .providers import ProviderError

PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING, "maxItems": 12}
TASK = {"type": "object", "additionalProperties": False, "required": ["id", "instruction"],
        "properties": {"id": STRING, "instruction": STRING, "kind": STRING,
                       "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                       "complexity": {"type": "integer", "minimum": 1, "maximum": 3},
                       "read_files": STRINGS, "write_files": {**STRINGS, "maxItems": 4},
                       "acceptance": STRINGS, "depends_on": {**STRINGS, "maxItems": 64},
                       "preferred_provider": STRING}}


def schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


TOOLS = [
    {"name": "relay_status", "description": "Read configured model profiles, exact workspace grants and call limits. No API calls.",
     "inputSchema": schema(), "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "relay_plan", "description": "Freeze bounded coding tasks and source files. Retain complex/sensitive/dependent work with the host. Preview exact API destinations without network calls.",
     "inputSchema": schema({"workspace": STRING, "tasks": {"type": "array", "items": TASK, "minItems": 1, "maxItems": 64}}, ("workspace", "tasks")),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
    {"name": "relay_run", "description": "Dispatch a frozen plan to configured user API models. Consumes API/campus quota under saved grants. Same plan ID never automatically resends. Workers return candidates only.",
     "inputSchema": schema({"plan_id": STRING}, ("plan_id",)),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}},
    {"name": "relay_job", "description": "Read compact per-task progress, actual reported usage and uncertain outcomes. No provider calls.",
     "inputSchema": schema({"plan_id": STRING}, ("plan_id",)),
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "relay_result", "description": "Read one untrusted candidate and diff. Host must review before applying and testing. Reports source drift. Never modifies the workspace.",
     "inputSchema": schema({"plan_id": STRING, "task_id": STRING}, ("plan_id", "task_id")),
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "relay_cancel", "description": "Stop queued work and discard late candidates. In-flight API requests may already be billed.",
     "inputSchema": schema({"plan_id": STRING}, ("plan_id",)),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "relay_setup", "description": "Open local connection settings for the user to configure multiple models, credentials and workspace grants. Never asks for API keys in chat.",
     "inputSchema": schema(), "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
]
for tool in TOOLS:
    tool["outputSchema"] = OUTPUT_SCHEMAS[tool["name"]]


def validate(value, definition):
    kind = definition.get("type")
    matches = {"object": isinstance(value, dict), "array": isinstance(value, list),
               "string": isinstance(value, str), "integer": type(value) is int}
    require(matches.get(kind, True), "invalid_arguments", "Tool arguments have an invalid type.")
    if kind == "object":
        properties = definition.get("properties", {})
        require(set(definition.get("required", [])) <= set(value) and set(value) <= set(properties),
                "invalid_arguments", "Tool arguments have unknown or missing fields.")
        for key, item in value.items():
            validate(item, properties[key])
    elif kind == "array":
        require(definition.get("minItems", 0) <= len(value) <= definition.get("maxItems", 64),
                "invalid_arguments", "Too many or too few array entries.")
        for item in value:
            validate(item, definition["items"])
    elif kind == "integer":
        require(definition.get("minimum", value) <= value <= definition.get("maximum", value),
                "invalid_arguments", "Integer argument is outside its limits.")
    elif kind == "string":
        require(len(value) <= 8000, "invalid_arguments", "String argument is too large.")
    if "enum" in definition:
        require(value in definition["enum"], "invalid_arguments", "Unsupported argument value.")


def open_setup():
    if getattr(sys, "frozen", False):
        command = [sys.executable, "setup"]
    else:
        command = [sys.executable, "-m", "code_relay", "setup"]
    kwargs = {"cwd": str(Path(__file__).resolve().parents[1])} if not getattr(sys, "frozen", False) else {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **kwargs)
    return {"status": "opened", "note": "Enter API credentials only in local settings. Live provider acceptance remains separate."}


class Server:
    def __init__(self, *, configuration: Path | None = None, state_dir: Path | None = None):
        self.configuration = configuration or config_path()
        self.state_dir = state_dir
        self.relay = None
        self.initialized = False

    def get_relay(self):
        config = load_config(self.configuration)
        if self.relay is None or self.relay.signature != digest(config):
            self.relay = Relay(config, state_dir=self.state_dir, source_config=self.configuration)
        return self.relay

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid JSON-RPC request."}}
        request_id = message.get("id")
        if "id" in message and not (isinstance(request_id, str) or type(request_id) is int):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request ID."}}
        method = message.get("method")
        if not isinstance(method, str):
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid request method."}}
        if "id" not in message:
            return None
        params = message.get("params", {})
        reply = {"jsonrpc": "2.0", "id": request_id}
        if not isinstance(params, dict):
            return reply | {"error": {"code": -32602, "message": "Parameters must be an object."}}
        if method == "initialize":
            self.initialized = True
            requested = params.get("protocolVersion")
            return reply | {"result": {"protocolVersion": requested if requested in PROTOCOLS else PROTOCOLS[0],
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "code-relay", "version": __version__},
                          "instructions": "Host owns architecture and review. API worker output is untrusted candidate code; never auto-apply or execute it."}}
        if method == "ping":
            return reply | {"result": {}}
        if not self.initialized:
            return reply | {"error": {"code": -32000, "message": "Initialize the server first."}}
        if method == "tools/list":
            return reply | {"result": {"tools": TOOLS}}
        if method != "tools/call":
            return reply | {"error": {"code": -32601, "message": "Method not found."}}
        selected = next((tool for tool in TOOLS if tool["name"] == params.get("name")), None)
        if selected is None:
            return reply | {"error": {"code": -32602, "message": "Unknown tool."}}
        result = None
        arguments = params.get("arguments", {})
        try:
            validate(arguments, selected["inputSchema"])
            if selected["name"] == "relay_setup":
                result = open_setup()
            else:
                function = getattr(self.get_relay(), selected["name"].removeprefix("relay_"))
                result = function(**arguments)
            if not isinstance(result, dict):
                raise RelayError("invalid_output", "The local result is not an object. Inspect status before retrying.")
            result = {**result, "contract_version": CONTRACT_VERSION}
            validate_output(selected["name"], result)
            for key in ("plan_id", "task_id"):
                if key in arguments:
                    require(result.get(key) == arguments[key], "invalid_output",
                            "The local result does not match the requested identifier. Inspect status before retrying.")
            failed = "error" in result
        except (RelayError, ProviderError) as exc:
            result = error_output(exc.code, str(exc), arguments, result)
            failed = True
        except Exception:
            result = error_output("internal_error", "The local operation failed. Check local settings and job status; do not automatically resend.", arguments, result)
            failed = True
        try:
            validate_output(selected["name"], result)
        except RelayError:
            result = error_output("invalid_output", "The local result failed its output contract. Inspect status before retrying; no request was repeated.", arguments, result)
            failed = True
            validate_output(selected["name"], result)
        return reply | {"result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                                    "structuredContent": result, "isError": failed}}


def serve(configuration=None, state_dir=None):
    server = Server(configuration=configuration, state_dir=state_dir)
    incoming, outgoing = sys.stdin.buffer, sys.stdout.buffer
    while True:
        line = incoming.readline(1048577)
        if not line:
            break
        if len(line) > 1048576:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Message exceeds 1 MiB."}}
            outgoing.write(json_bytes(response) + b"\n")
            outgoing.flush()
            break
        try:
            message = strict_json(line)
            response = server.handle(message)
        except (ValueError, UnicodeError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON."}}
        if response is not None:
            outgoing.write(json_bytes(response) + b"\n")
            outgoing.flush()
    # EOF cancels this host's outstanding work instead of waiting indefinitely.
    if server.relay:
        for event, thread in server.relay._active.values():
            if thread.is_alive():
                event.set()
