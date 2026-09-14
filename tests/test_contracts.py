"""Public MCP output contracts exercised with isolated, synthetic local work.

The real planner and coordinator run, but their provider caller is synthetic.
Setup is replaced at its UI boundary; no API or host process is launched.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from code_relay.common import RelayError
from code_relay.config import validate_config
from code_relay.contracts import OUTPUT_SCHEMAS, validate_output
from code_relay.core import Relay
from code_relay.providers import ProviderError
from code_relay.server import Server


TOOL_NAMES = {
    "relay_status", "relay_plan", "relay_run", "relay_job",
    "relay_result", "relay_cancel", "relay_setup",
}


class OutputContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="code-relay-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "synthetic-workspace"
        self.root.mkdir()
        (self.root / "sample.py").write_text("answer = 1\n", encoding="utf-8")
        self.state = self.base / "private-state"
        self.configuration = self.base / "synthetic-config.json"
        self.config = validate_config({
            "workspaces": [str(self.root)], "network_enabled": True,
            "max_parallel": 1,
            "providers": [{"id": "worker", "protocol": "openai",
                           "base_url": "https://synthetic.invalid/v1",
                           "model": "exact-synthetic-model", "key_env": "RELAY_CONTRACT_TEST_KEY",
                           "concurrency": 1}],
        })
        self.configuration.write_text(json.dumps(self.config), encoding="utf-8")
        environment = patch.dict(os.environ, {"RELAY_CONTRACT_TEST_KEY": "synthetic-contract-credential"})
        environment.start()
        self.addCleanup(environment.stop)
        no_process = patch("code_relay.server.subprocess.Popen", side_effect=AssertionError(
            "Contract tests must not launch a host or setup process."))
        no_process.start()
        self.addCleanup(no_process.stop)
        self.provider_calls = []
        self.usage = None
        self.gates = []
        self.relay = Relay(self.config, state_dir=self.state, source_config=self.configuration,
                           caller=self.fake_caller)
        self.addCleanup(self.cleanup_workers)
        self.server = Server(configuration=self.configuration, state_dir=self.state)
        self.server.relay = self.relay
        self.request_id = 0
        self.server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                            "params": {"protocolVersion": "2025-11-25"}})

    def cleanup_workers(self):
        for event in self.gates:
            event.set()
        with self.relay._lock:
            active = list(self.relay._active.values())
        for event, thread in active:
            event.set()
            thread.join(5)
            if thread.is_alive():
                self.fail("A synthetic contract worker did not terminate.")

    def gate(self):
        event = threading.Event()
        self.gates.append(event)
        return event

    def fake_caller(self, provider, key, system, user, *, cancelled=None):
        payload = json.loads(user)
        self.provider_calls.append(payload["task"]["id"])
        return {"text": json.dumps({"summary": "Updated the numeric fixture.", "files": [
                    {"path": payload["task"]["write_files"][0], "content": "answer = 2\n"}
                ]}), "usage": copy.deepcopy(self.usage), "elapsed_ms": 1, "outcome": "completed"}

    def task(self, **changes):
        return {"id": "one", "instruction": "Update the numeric fixture.",
                "kind": "mechanical_edit", "risk": "low", "complexity": 1,
                "read_files": ["sample.py"], "write_files": ["sample.py"],
                "acceptance": ["The fixture value equals two."], **changes}

    def call(self, name, arguments=None):
        self.request_id += 1
        answer = self.server.handle({"jsonrpc": "2.0", "id": self.request_id,
                                     "method": "tools/call",
                                     "params": {"name": name, "arguments": arguments or {}}})
        self.assertNotIn("error", answer, answer)
        return answer["result"]

    def assert_result(self, tool, result, *, error=False):
        self.assertIs(result["isError"], error, result)
        structured = result["structuredContent"]
        self.assertEqual(structured["contract_version"], "1.0")
        texts = [block["text"] for block in result["content"] if block["type"] == "text"]
        self.assertEqual(len(texts), 1)
        self.assertEqual(json.loads(texts[0]), structured)
        json.dumps(structured, allow_nan=False)
        validate_output(tool, structured)
        if error:
            self.assertIn(structured["recovery"], {"inspect_status_before_retry", "check_settings_or_arguments"})
        return structured

    def plan(self):
        return self.assert_result("relay_plan", self.call("relay_plan", {
            "workspace": str(self.root), "tasks": [self.task()]}))

    def terminal(self, plan_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.assert_result("relay_job", self.call("relay_job", {"plan_id": plan_id}))
            if result["state"] in {"completed", "needs_attention", "cancelled", "interrupted"}:
                with self.relay._lock:
                    active = self.relay._active.get(plan_id)
                if active is not None:
                    active[1].join(2)
                return result
            time.sleep(0.01)
        self.fail("The synthetic lifecycle did not reach a terminal state.")

    def completed(self):
        plan = self.plan()
        self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
        final = self.terminal(plan["plan_id"])
        self.assertEqual(final["state"], "completed")
        candidate = self.assert_result("relay_result", self.call("relay_result", {
            "plan_id": plan["plan_id"], "task_id": "one"}))
        return plan, final, candidate

    def test_all_seven_tools_publish_bounded_output_schemas_and_resolvable_refs(self):
        answer = self.server.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
        tools = answer["result"]["tools"]
        self.assertEqual({tool["name"] for tool in tools}, TOOL_NAMES)
        self.assertEqual(set(OUTPUT_SCHEMAS), TOOL_NAMES)
        self.assertEqual(len(tools), 7)
        for tool in tools:
            with self.subTest(tool=tool["name"]):
                schema = tool["outputSchema"]
                self.assertEqual(schema, OUTPUT_SCHEMAS[tool["name"]])
                self.assertEqual(schema["type"], "object")
                self.assertGreaterEqual(len(schema["anyOf"]), 2)
                self.assertIsInstance(schema["$defs"], dict)
                self.assertTrue(schema["$defs"])
                references = []
                def visit(value):
                    if isinstance(value, dict):
                        if "$ref" in value:
                            reference = value["$ref"]
                            self.assertTrue(reference.startswith("#/"), reference)
                            target = schema
                            for part in reference[2:].split("/"):
                                target = target[part.replace("~1", "/").replace("~0", "~")]
                            self.assertIsInstance(target, dict)
                            references.append(reference)
                        for item in value.values():
                            visit(item)
                    elif isinstance(value, list):
                        for item in value:
                            visit(item)
                visit(schema)
                self.assertTrue(references)
                json.dumps(schema, allow_nan=False)
        self.assertEqual(self.provider_calls, [])

    def test_real_lifecycle_preserves_old_shapes_and_explicit_null_usage(self):
        original_status = self.relay.status()
        status = self.assert_result("relay_status", self.call("relay_status"))
        self.assertEqual({key: value for key, value in status.items() if key != "contract_version"},
                         original_status)
        plan = self.plan()
        self.assertEqual(plan["dispatch_count"], 1)
        pending = self.assert_result("relay_job", self.call("relay_job", {"plan_id": plan["plan_id"]}))
        self.assertEqual(pending["state"], "planned")
        self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
        final = self.terminal(plan["plan_id"])
        self.assertEqual(final["state"], "completed")
        self.assertIsNone(final["actual_cost"])
        self.assertIsNone(final["tasks"][0]["usage"])
        candidate = self.assert_result("relay_result", self.call("relay_result", {
            "plan_id": plan["plan_id"], "task_id": "one"}))
        self.assertIsNone(candidate["usage"])
        self.assertEqual(candidate["disposition"], "needs_host_review")
        self.assertFalse(candidate["workspace_modified"])
        self.assertTrue(candidate["source_still_matches"])
        artifact_bytes = Path(candidate["artifact_path"]).read_bytes()
        self.assertEqual(candidate["artifact"]["path"], candidate["artifact_path"])
        self.assertEqual(candidate["artifact"]["media_type"], "application/json")
        self.assertEqual(candidate["artifact"]["size_bytes"], len(artifact_bytes))
        self.assertEqual(candidate["artifact"]["sha256"], hashlib.sha256(artifact_bytes).hexdigest())
        self.assertIn("+answer = 2", candidate["diff"])
        unchanged = self.assert_result("relay_cancel", self.call("relay_cancel", {"plan_id": plan["plan_id"]}))
        self.assertEqual(unchanged["state"], "completed")
        self.assertEqual(self.provider_calls, ["one"])
        self.assertEqual((self.root / "sample.py").read_text(), "answer = 1\n")

    def test_cancel_before_run_keeps_marker_and_never_reserves_or_dispatches(self):
        plan = self.plan()
        cancellation = self.assert_result("relay_cancel", self.call("relay_cancel", {"plan_id": plan["plan_id"]}))
        self.assertEqual(cancellation["state"], "cancellation_requested")
        pending = self.assert_result("relay_job", self.call("relay_job", {"plan_id": plan["plan_id"]}))
        self.assertEqual(pending["state"], "planned")
        self.assertTrue(pending["cancellation_requested"])
        with patch.object(self.relay, "_reserve", wraps=self.relay._reserve) as reserve:
            for _ in range(2):
                cancelled = self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
                self.assertEqual(cancelled["state"], "planned")
                self.assertTrue(cancelled["cancellation_requested"])
        reserve.assert_not_called()
        self.assertEqual(self.provider_calls, [])
        self.assertFalse((self.state / "budget.json").exists())
        self.assertFalse((self.state / plan["plan_id"] / "run.json").exists())
        self.assertFalse((self.state / plan["plan_id"] / "claimed").exists())

    def test_queued_running_cancellation_and_cancelled_result_error_are_schema_valid(self):
        execute_entered, release_execute = self.gate(), self.gate()
        caller_entered, release_caller = self.gate(), self.gate()
        original_execute = self.relay._execute
        def delayed_execute(*args):
            execute_entered.set()
            if not release_execute.wait(4):
                raise AssertionError("Synthetic queue barrier timed out.")
            return original_execute(*args)
        def delayed_caller(*args, **kwargs):
            response = self.fake_caller(*args, **kwargs)
            caller_entered.set()
            if not release_caller.wait(4):
                raise AssertionError("Synthetic response barrier timed out.")
            return response
        self.relay.caller = delayed_caller
        plan = self.plan()
        with patch.object(self.relay, "_execute", side_effect=delayed_execute):
            queued = self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
            self.assertTrue(execute_entered.wait(2))
            self.assertEqual(queued["state"], "queued")
            self.assertIsNone(queued["finished_at"])
            self.assertNotIn("usage", queued["tasks"][0])
            release_execute.set()
            self.assertTrue(caller_entered.wait(2))
            running = self.assert_result("relay_job", self.call("relay_job", {"plan_id": plan["plan_id"]}))
            self.assertEqual(running["state"], "running")
            cancellation = self.assert_result("relay_cancel", self.call("relay_cancel", {"plan_id": plan["plan_id"]}))
            self.assertEqual(cancellation["state"], "cancellation_requested")
            release_caller.set()
            final = self.terminal(plan["plan_id"])
        self.assertEqual(final["state"], "cancelled")
        self.assertEqual(final["tasks"][0]["state"], "cancelled_after_dispatch")
        error = self.assert_result("relay_result", self.call("relay_result", {
            "plan_id": plan["plan_id"], "task_id": "one"}), error=True)
        self.assertEqual(error["error"]["code"], "cancelled")
        self.assertEqual(error["plan_id"], plan["plan_id"])
        self.assertEqual(error["task_id"], "one")
        self.assertEqual(self.provider_calls, ["one"])

    def test_interrupted_execution_and_partial_claim_have_valid_lifecycle_contracts(self):
        plan = self.plan()
        with patch("code_relay.core.ThreadPoolExecutor", side_effect=RuntimeError("Synthetic executor failure")):
            self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
            interrupted = self.terminal(plan["plan_id"])
        self.assertEqual(interrupted["state"], "interrupted")
        self.assert_result("relay_cancel", self.call("relay_cancel", {"plan_id": plan["plan_id"]}))
        another = self.plan()
        (self.state / another["plan_id"] / "claimed").write_text("Synthetic interrupted start", encoding="utf-8")
        partial = self.assert_result("relay_job", self.call("relay_job", {"plan_id": another["plan_id"]}))
        self.assertEqual(partial["state"], "interrupted_or_starting")
        repeated = self.assert_result("relay_run", self.call("relay_run", {"plan_id": another["plan_id"]}))
        self.assertEqual(repeated["state"], "interrupted_or_starting")
        self.assertEqual(self.provider_calls, [])

    def test_reported_zero_usage_and_unavailable_counts_keep_distinct_meanings(self):
        self.usage = {"input_tokens": 0, "output_tokens": 2, "cached_input_tokens": None,
                      "reasoning_tokens": None}
        _, final, candidate = self.completed()
        self.assertEqual(final["tasks"][0]["usage"], self.usage)
        self.assertEqual(candidate["usage"], self.usage)
        self.assertEqual(candidate["usage"]["input_tokens"], 0)
        self.assertIsNone(candidate["usage"]["cached_input_tokens"])

    def test_provider_failure_is_needs_attention_with_nullable_usage(self):
        def failed_caller(*args, **kwargs):
            self.provider_calls.append("one")
            raise ProviderError("synthetic_failure", "Synthetic provider failure.", uncertain=True, usage=None)
        self.relay.caller = failed_caller
        plan = self.plan()
        self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
        final = self.terminal(plan["plan_id"])
        self.assertEqual(final["state"], "needs_attention")
        self.assertEqual(final["tasks"][0]["state"], "escalated")
        self.assertIsNone(final["tasks"][0]["usage"])
        self.assertTrue(final["tasks"][0]["uncertain"])

    def test_host_owned_plan_has_null_destination_and_cannot_dispatch(self):
        plan = self.assert_result("relay_plan", self.call("relay_plan", {
            "workspace": str(self.root), "tasks": [self.task(risk="high")]}))
        self.assertEqual(plan["dispatch_count"], 0)
        row = plan["tasks"][0]
        self.assertEqual(row["owner"], "host")
        for key in ["profile", "model", "endpoint"]:
            self.assertIsNone(row[key])
        error = self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}), error=True)
        self.assertEqual(error["error"]["code"], "host_only")
        self.assertEqual(error["plan_id"], plan["plan_id"])
        self.assertEqual(self.provider_calls, [])

    def test_setup_success_and_execution_failure_use_the_same_output_contract(self):
        with patch("code_relay.server.open_setup", return_value={"status": "opened", "note": "Synthetic setup."}):
            opened = self.assert_result("relay_setup", self.call("relay_setup"))
        self.assertEqual(opened["status"], "opened")
        with patch("code_relay.server.open_setup", side_effect=OSError("Private diagnostic must not escape")):
            failed = self.assert_result("relay_setup", self.call("relay_setup"), error=True)
        self.assertEqual(failed["error"]["code"], "internal_error")
        self.assertNotIn("Private diagnostic", json.dumps(failed))
        self.assertEqual(self.provider_calls, [])

    def test_validation_errors_preserve_valid_identifiers_and_drop_invalid_ones(self):
        missing = self.assert_result("relay_result", self.call("relay_result", {
            "plan_id": "p-missing", "task_id": "one"}), error=True)
        self.assertEqual(missing["error"]["code"], "unknown_plan")
        self.assertEqual(missing["plan_id"], "p-missing")
        self.assertEqual(missing["task_id"], "one")
        invalid = self.assert_result("relay_result", self.call("relay_result", {
            "plan_id": "p-missing", "task_id": "../not-an-id"}), error=True)
        self.assertEqual(invalid["plan_id"], "p-missing")
        self.assertNotIn("task_id", invalid)
        self.assertEqual(self.provider_calls, [])

    def test_every_tool_rejects_malformed_backend_output_once_and_retains_known_ids(self):
        arguments = {
            "relay_status": {}, "relay_plan": {"workspace": str(self.root), "tasks": [self.task()]},
            "relay_run": {"plan_id": "p-known"}, "relay_job": {"plan_id": "p-known"},
            "relay_result": {"plan_id": "p-known", "task_id": "one"},
            "relay_cancel": {"plan_id": "p-known"}, "relay_setup": {},
        }
        for tool in sorted(TOOL_NAMES):
            with self.subTest(tool=tool):
                raw = {"unexpected": "PRIVATE_BACKEND_SENTINEL"}
                if tool == "relay_plan":
                    raw["plan_id"] = "p-created"
                if tool == "relay_result":
                    raw.update({"plan_id": "../unsafe", "task_id": 123})
                if tool == "relay_setup":
                    replacement = patch("code_relay.server.open_setup", return_value=raw)
                else:
                    replacement = patch.object(self.relay, tool.removeprefix("relay_"), return_value=raw)
                with replacement as backend:
                    result = self.assert_result(tool, self.call(tool, arguments[tool]), error=True)
                backend.assert_called_once()
                self.assertEqual(result["error"]["code"], "invalid_output")
                self.assertNotIn("PRIVATE_BACKEND_SENTINEL", json.dumps(result))
                for key in ["plan_id", "task_id"]:
                    if key in arguments[tool]:
                        self.assertEqual(result[key], arguments[tool][key])
                if tool == "relay_plan":
                    self.assertEqual(result["plan_id"], "p-created")
        self.assertEqual(self.provider_calls, [])

    def test_artifact_hash_and_size_match_pretty_formatted_bytes_on_disk(self):
        plan, _, first = self.completed()
        path = Path(first["artifact_path"])
        stored = json.loads(path.read_bytes())
        pretty = (json.dumps(stored, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.assertNotEqual(path.read_bytes(), pretty)
        path.write_bytes(pretty)
        reread = self.assert_result("relay_result", self.call("relay_result", {
            "plan_id": plan["plan_id"], "task_id": "one"}))
        self.assertEqual(reread["artifact"]["path"], str(path))
        self.assertEqual(reread["artifact"]["size_bytes"], len(pretty))
        self.assertEqual(reread["artifact"]["sha256"], hashlib.sha256(pretty).hexdigest())
        self.assertNotEqual(reread["artifact"]["sha256"], first["artifact"]["sha256"])
        self.assertEqual(self.provider_calls, ["one"])

    def test_output_identifiers_with_trailing_line_breaks_are_rejected(self):
        valid = {"contract_version": "1.0", "error": {
            "code": "synthetic_error", "message": "Synthetic error."},
                 "recovery": "inspect_status_before_retry", "plan_id": "p-known", "task_id": "one"}
        for tool in sorted(TOOL_NAMES):
            for field in ["plan_id", "task_id"]:
                for ending in ["\n", "\r\n", "\r", "\u2028"]:
                    with self.subTest(tool=tool, field=field, suffix=repr(ending)):
                        malformed = copy.deepcopy(valid)
                        malformed[field] += ending
                        with self.assertRaises(RelayError) as error:
                            validate_output(tool, malformed)
                        self.assertEqual(error.exception.code, "invalid_output")
        plan, _, candidate = self.completed()
        for tool, raw, field in [("relay_plan", plan, "plan_id"), ("relay_result", candidate, "task_id")]:
            malformed = copy.deepcopy(raw)
            malformed[field] += "\n"
            with self.assertRaises(RelayError) as error:
                validate_output(tool, malformed)
            self.assertEqual(error.exception.code, "invalid_output")

    def test_backend_identifier_mismatch_is_an_error_with_requested_ids(self):
        plan, final, candidate = self.completed()
        cases = [("relay_run", final), ("relay_job", final), ("relay_cancel", final),
                 ("relay_result", candidate)]
        for tool, payload in cases:
            with self.subTest(tool=tool):
                arguments = {"plan_id": plan["plan_id"]}
                wrong = copy.deepcopy(payload)
                wrong["plan_id"] = "p-other-operation"
                if tool == "relay_result":
                    arguments["task_id"] = "one"
                    wrong["task_id"] = "different-task"
                # The payload is individually schema-valid: the defect is correlation.
                validate_output(tool, wrong)
                with patch.object(self.relay, tool.removeprefix("relay_"), return_value=wrong) as backend:
                    rejected = self.assert_result(tool, self.call(tool, arguments), error=True)
                backend.assert_called_once_with(**arguments)
                self.assertEqual(rejected["error"]["code"], "invalid_output")
                self.assertEqual(rejected["plan_id"], plan["plan_id"])
                if "task_id" in arguments:
                    self.assertEqual(rejected["task_id"], "one")
        self.assertEqual(self.provider_calls, ["one"])

    def test_malformed_output_after_real_dispatch_does_not_repeat_the_side_effect(self):
        plan = self.plan()
        original_run = self.relay.run
        def malformed_after_dispatch(plan_id):
            original_run(plan_id)
            return {"plan_id": plan_id, "state": "unknown_backend_state"}
        with patch.object(self.relay, "run", side_effect=malformed_after_dispatch) as backend:
            error = self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}), error=True)
        backend.assert_called_once_with(plan_id=plan["plan_id"])
        self.assertEqual(error["error"]["code"], "invalid_output")
        self.assertEqual(error["plan_id"], plan["plan_id"])
        self.assertEqual(self.terminal(plan["plan_id"])["state"], "completed")
        self.assert_result("relay_run", self.call("relay_run", {"plan_id": plan["plan_id"]}))
        self.assertEqual(self.provider_calls, ["one"])

    def test_valid_backend_error_payload_sets_mcp_is_error(self):
        raw = {"contract_version": "1.0", "error": {
            "code": "synthetic_error", "message": "Synthetic backend error."},
               "recovery": "check_settings_or_arguments"}
        with patch.object(self.relay, "status", return_value=raw):
            error = self.assert_result("relay_status", self.call("relay_status"), error=True)
        self.assertEqual(error["error"]["code"], "synthetic_error")

    def test_all_tool_error_contracts_require_version_code_and_message(self):
        valid = {"contract_version": "1.0", "error": {"code": "synthetic_error", "message": "Synthetic error."},
                 "plan_id": "p-known", "task_id": "one", "recovery": "inspect_status_before_retry"}
        malformed = [
            {}, {"error": valid["error"]}, {**valid, "contract_version": "99.0"},
            {**valid, "error": {"code": 4, "message": "wrong code type"}},
            {**valid, "error": {"code": "synthetic_error"}},
            {**valid, "plan_id": "../unsafe"}, {**valid, "recovery": "automatically_repeat_write"},
        ]
        for tool in sorted(TOOL_NAMES):
            validate_output(tool, valid)
            for number, value in enumerate(malformed):
                with self.subTest(tool=tool, invalid_case=number):
                    with self.assertRaises(RelayError) as error:
                        validate_output(tool, value)
                    self.assertEqual(error.exception.code, "invalid_output")

    def test_validator_rejects_malformed_lifecycle_fields_and_candidate_payloads(self):
        plan, final, candidate = self.completed()
        cases = []
        missing_id = copy.deepcopy(plan)
        del missing_id["plan_id"]
        cases.append(("relay_plan", missing_id))
        wrong_tasks = copy.deepcopy(plan)
        wrong_tasks["tasks"] = "not a task array"
        cases.append(("relay_plan", wrong_tasks))
        for field, value in [("state", "unsupported_state"), ("submission_attempts", True),
                             ("actual_cost", "not calculated")]:
            bad = copy.deepcopy(final)
            bad[field] = value
            cases.append(("relay_job", bad))
        bad_task = copy.deepcopy(final)
        bad_task["tasks"][0]["state"] = "self_approved"
        cases.append(("relay_job", bad_task))
        for field, value in [("workspace_modified", True), ("usage", {"input_tokens": -1}),
                             ("artifact_path", None), ("files", [{"path": "sample.py", "content": 123}])]:
            bad = copy.deepcopy(candidate)
            bad[field] = value
            cases.append(("relay_result", bad))
        for field, value in [("sha256", "not-a-hash"), ("size_bytes", 0), ("media_type", "text/html")]:
            bad = copy.deepcopy(candidate)
            bad["artifact"][field] = value
            cases.append(("relay_result", bad))
        for number, (tool, value) in enumerate(cases):
            with self.subTest(tool=tool, invalid_case=number):
                with self.assertRaises(RelayError) as error:
                    validate_output(tool, value)
                self.assertEqual(error.exception.code, "invalid_output")


if __name__ == "__main__":
    unittest.main()
