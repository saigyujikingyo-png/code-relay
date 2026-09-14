"""Versioned JSON Schema output contracts, validated before MCP delivery.

The validator implements only the vocabulary used below. It is not a general
JSON Schema implementation. No model output or remote schema is executed.
"""
from __future__ import annotations

import re

from .common import RelayError, json_bytes

CONTRACT_VERSION = "1.0"


def text(limit=8000, **extra):
    return {"type": "string", "maxLength": limit, **extra}


def integer(low=0, high=None):
    return {"type": "integer", "minimum": low, **({"maximum": high} if high is not None else {})}


def obj(properties, optional=()):
    return {"type": "object", "properties": properties,
            "required": [key for key in properties if key not in optional], "additionalProperties": False}


def array(items, maximum, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def nullable(definition):
    return {"anyOf": [definition, {"type": "null"}]}


def choice(*values):
    return text(80, enum=list(values))


BOOL = {"type": "boolean"}
FALSE = {"type": "boolean", "enum": [False]}
TRUE = {"type": "boolean", "enum": [True]}
NULL = {"type": "null"}
ID = text(40, pattern=r"^[a-z][a-z0-9-]{0,39}(?![\s\S])")
PATH = text(32768)
TIME = text(80, pattern=r"^\d{4}-\d{2}-\d{2}T")
VERSION = choice(CONTRACT_VERSION)
USAGE = nullable(obj({key: nullable(integer()) for key in
                      ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")}))
ERROR = obj({"contract_version": VERSION,
             "error": obj({"code": text(80, pattern=r"^[a-z][a-z0-9_]*$"), "message": text()}),
             "recovery": choice("inspect_status_before_retry", "check_settings_or_arguments"),
             "plan_id": ID, "task_id": ID}, optional=("plan_id", "task_id"))

PROFILE = obj({"id": ID, "protocol": choice("openai", "anthropic"), "base_url": text(2048),
               "model": text(512), "key_env": text(128),
               "capabilities": array(choice("tests", "docs", "boilerplate", "mechanical_edit"), 4, 1),
               "priority": integer(0, 1000), "concurrency": integer(1, 4),
               "input_limit_bytes": integer(1, 262144), "output_limit_tokens": integer(1, 16384),
               "enabled": BOOL, "credential_available": BOOL, "live_acceptance": choice("unverified")})
STATUS = obj({"contract_version": VERSION, "version": text(80), "network_enabled": BOOL,
              "profiles": array(PROFILE, 32), "workspaces": array(PATH, 32),
              "limits": obj({"max_parallel": integer(1, 4), "max_requests_per_run": integer(1, 64),
                             "daily_request_limit": integer(1, 10000), "state_limit_mb": integer(8, 1024)}),
              "account_dependency": text(), "state_directory": PATH, "automatic_workspace_writes": FALSE})
PLAN_TASK = obj({"id": ID, "owner": choice("api_worker", "host"), "profile": nullable(ID),
                 "model": nullable(text(512)), "endpoint": nullable(text(2048)), "reason": text(),
                 "read_files": array(PATH, 12), "write_files": array(PATH, 4),
                 "input_bytes": integer(), "output_token_limit": integer(0, 16384)})
PLAN = obj({"contract_version": VERSION, "plan_id": ID, "workspace": PATH,
            "tasks": array(PLAN_TASK, 64, 1), "dispatch_count": integer(0, 64),
            "network_calls_made": {"type": "integer", "enum": [0]}, "review_required": TRUE,
            "actual_cost": NULL, "note": text()})
JOB_TASK = obj({"id": ID, "profile": nullable(ID), "reason": text(),
                "state": choice("queued", "host_owned", "running", "cancelled_before_send",
                                "cancelled_after_dispatch", "needs_host_review", "escalated"),
                "uncertain": BOOL, "usage": {"$ref": "#/$defs/usage"},
                "elapsed_ms": nullable(integer()), "model": text(512),
                "error_code": text(80, pattern=r"^[a-z][a-z0-9_]*$")},
               optional=("uncertain", "usage", "elapsed_ms", "model", "error_code"))
JOB = obj({"contract_version": VERSION, "plan_id": ID,
           "state": choice("queued", "running", "completed", "needs_attention", "cancelled", "interrupted"),
           "started_at": TIME, "finished_at": nullable(TIME),
           "reserved_requests": integer(1, 64), "submission_attempts": integer(0, 64),
           "actual_cost": NULL, "tasks": array(JOB_TASK, 64, 1), "reason": text(),
           "observation": text(), "cancellation_requested": TRUE},
          optional=("reason", "observation", "cancellation_requested"))
JOB_STUB = obj({"contract_version": VERSION, "plan_id": ID,
                "state": choice("planned", "interrupted_or_starting"), "retry_policy": text(),
                "cancellation_requested": TRUE}, optional=("cancellation_requested",))
CANCEL = obj({"contract_version": VERSION, "plan_id": ID,
              "state": choice("cancellation_requested"), "note": text()})
ARTIFACT = obj({"path": PATH, "media_type": choice("application/json"), "size_bytes": integer(1, 8388608),
                "sha256": text(64, minLength=64, pattern=r"^[0-9a-f]{64}$")})
RESULT = obj({"contract_version": VERSION, "plan_id": ID, "task_id": ID, "profile": ID,
              "disposition": choice("needs_host_review"), "untrusted_worker_output": TRUE,
              "summary": text(2000), "files": array(obj({"path": PATH, "content": text(524288)}), 4, 1),
              "diff": text(4194304), "acceptance": array(text(2000), 12),
              "usage": {"$ref": "#/$defs/usage"}, "workspace_modified": FALSE,
              "review_instruction": text(), "source_still_matches": BOOL,
              "artifact_path": PATH, "artifact": ARTIFACT})
SETUP = obj({"contract_version": VERSION, "status": choice("opened"), "note": text()})


def contract(*successes, usage=False):
    definitions = {"error": ERROR}
    if usage:
        definitions["usage"] = USAGE
    return {"type": "object", "$defs": definitions,
            "anyOf": [*successes, {"$ref": "#/$defs/error"}]}


OUTPUT_SCHEMAS = {
    "relay_status": contract(STATUS),
    "relay_plan": contract(PLAN),
    "relay_run": contract(JOB, JOB_STUB, usage=True),
    "relay_job": contract(JOB, JOB_STUB, usage=True),
    "relay_result": contract(RESULT, usage=True),
    "relay_cancel": contract(CANCEL, JOB, usage=True),
    "relay_setup": contract(SETUP),
}


def _validate(value, definition, root):
    if "$ref" in definition:
        _validate(value, root["$defs"][definition["$ref"].removeprefix("#/$defs/")], root)
        return
    if "anyOf" in definition:
        for branch in definition["anyOf"]:
            try:
                _validate(value, branch, root)
                return
            except ValueError:
                pass
        raise ValueError("No valid branch")
    kind = definition["type"]
    matches = {"object": type(value) is dict, "array": type(value) is list,
               "string": type(value) is str, "integer": type(value) is int,
               "boolean": type(value) is bool, "null": value is None}
    if not matches[kind] or ("enum" in definition and value not in definition["enum"]):
        raise ValueError("Invalid type or enum")
    if kind == "object":
        properties = definition["properties"]
        if not set(definition["required"]) <= set(value) or not set(value) <= set(properties):
            raise ValueError("Missing or unknown fields")
        for key, item in value.items():
            _validate(item, properties[key], root)
    elif kind == "array":
        if not definition["minItems"] <= len(value) <= definition["maxItems"]:
            raise ValueError("Invalid array length")
        for item in value:
            _validate(item, definition["items"], root)
    elif kind == "string":
        if not definition.get("minLength", 0) <= len(value) <= definition["maxLength"]:
            raise ValueError("Invalid string length")
        if "pattern" in definition and re.search(definition["pattern"], value) is None:
            raise ValueError("Invalid string pattern")
    elif kind == "integer":
        if not definition.get("minimum", value) <= value <= definition.get("maximum", value):
            raise ValueError("Invalid integer range")


def validate_output(tool_name, value):
    try:
        _validate(value, OUTPUT_SCHEMAS[tool_name], OUTPUT_SCHEMAS[tool_name])
        # Reject non-JSON values and lone Unicode surrogates before serialization.
        if len(json_bytes(value)) > 8 * 1024 * 1024:
            raise ValueError("Oversized output")
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise RelayError("invalid_output", "The local result failed its output contract. Inspect job status before retrying; no request was repeated.") from exc


def error_output(code, message, *contexts):
    result = {"contract_version": CONTRACT_VERSION, "error": {"code": code, "message": message},
              "recovery": "check_settings_or_arguments"}
    for context in contexts:
        if not isinstance(context, dict):
            continue
        for key in ("plan_id", "task_id"):
            value = context.get(key)
            if isinstance(value, str) and re.fullmatch(ID["pattern"], value):
                result.setdefault(key, value)
    if "plan_id" in result:
        result["recovery"] = "inspect_status_before_retry"
    return result
