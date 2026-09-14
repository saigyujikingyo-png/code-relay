"""Independent regression tests at Relay's public boundary.

All credentials, source and responses are synthetic. The injected callers never
open a network connection, execute generated code or modify source themselves.
"""
from __future__ import annotations

import copy
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from code_relay.common import RelayError
from code_relay.config import validate_config
from code_relay.core import Relay
from code_relay.providers import ProviderError
from code_relay.workspace import verify_snapshot


USAGE = {
    "input_tokens": 33, "output_tokens": 18,
    "cached_input_tokens": 4, "reasoning_tokens": 0,
}


def response(text=None, path="sample.py"):
    if text is None:
        text = json.dumps({
            "summary": "Updated the fixture.",
            "files": [{"path": path, "content": "answer = 2\n"}],
        })
    return {
        "text": text, "usage": dict(USAGE),
        "elapsed_ms": 1, "outcome": "completed",
    }


def _interrupted_process(config, state_dir, plan_id, dispatched):
    """A real second process is terminated only after it has claimed and sent."""
    def blocked_caller(*args, **kwargs):
        dispatched.set()
        threading.Event().wait(30)
        return response()

    relay = Relay(config, state_dir=Path(state_dir), caller=blocked_caller)
    relay.run(plan_id)
    threading.Event().wait(30)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="code-relay-boundary-")
        self.base = Path(self.temporary.name)
        self.root = self.base / "workspace"
        self.root.mkdir()
        (self.root / "sample.py").write_text("answer = 1\n", encoding="utf-8")
        (self.root / "other.py").write_text("answer = 1\n", encoding="utf-8")
        self.state = self.base / "private-state"
        self.config = validate_config({
            "workspaces": [str(self.root)], "network_enabled": True,
            "max_parallel": 1,
            "providers": [{
                "id": "worker", "protocol": "openai",
                "base_url": "https://synthetic.invalid/v1",
                "model": "exact-synthetic-model", "key_env": "RELAY_BOUNDARY_KEY",
                "concurrency": 1,
            }],
        })
        self.calls = []
        self.calls_lock = threading.Lock()
        self.gates = []
        self.relays = []
        self.threads = []
        self.processes = []
        self.addCleanup(self.temporary.cleanup)
        self.environment = patch.dict(
            os.environ, {"RELAY_BOUNDARY_KEY": "synthetic-boundary-credential"}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        # LIFO cleanup releases every barrier and joins workers before deleting
        # the temporary workspace, including when an assertion fails.
        self.addCleanup(self._cleanup_workers)
        self.relay = self.make_relay()

    def gate(self):
        event = threading.Event()
        self.gates.append(event)
        return event

    def make_relay(self, config=None, caller=None, **kwargs):
        relay = Relay(
            config or self.config, state_dir=self.state,
            caller=caller or self.fake_caller, **kwargs,
        )
        self.relays.append(relay)
        return relay

    def fake_caller(self, provider, key, system, user, *, cancelled=None):
        payload = json.loads(user)
        with self.calls_lock:
            self.calls.append({
                "provider": copy.deepcopy(provider), "payload": payload,
                "system": system, "user": user,
            })
        return response(path=payload["task"]["write_files"][0])

    def task(self, task_id="one", filename="sample.py", **overrides):
        return {
            "id": task_id, "instruction": "Change the numeric fixture to two.",
            "kind": "mechanical_edit", "risk": "low", "complexity": 1,
            "read_files": [filename], "write_files": [filename],
            "acceptance": ["The fixture value equals two."],
            **overrides,
        }

    def launch(self, function, name):
        outcomes = []

        def run():
            try:
                outcomes.append(("result", function()))
            except BaseException as error:
                outcomes.append(("error", error))

        thread = threading.Thread(target=run, name=name)
        self.threads.append(thread)
        thread.start()
        return thread, outcomes

    def join(self, thread):
        thread.join(timeout=6)
        self.assertFalse(thread.is_alive(), "A test-owned caller did not terminate.")

    def wait_terminal(self, relay, plan_id):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            status = relay.job(plan_id)
            if status["state"] in {
                "completed", "needs_attention", "cancelled", "interrupted",
            }:
                with relay._lock:
                    active = relay._active.get(plan_id)
                if active is not None:
                    self.join(active[1])
                return status
            time.sleep(0.01)
        self.fail("Relay did not reach a terminal state within the test deadline.")

    def finish(self, relay, plan_id):
        relay.run(plan_id)
        return self.wait_terminal(relay, plan_id)

    def _cleanup_workers(self):
        for gate in self.gates:
            gate.set()
        for process in self.processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=6)
            if process.is_alive():
                process.kill()
                process.join(timeout=6)
            process.close()
        for thread in self.threads:
            thread.join(timeout=6)
        for relay in self.relays:
            with relay._lock:
                active = list(relay._active.values())
            for event, thread in active:
                event.set()
                thread.join(timeout=6)
                if thread.is_alive():
                    raise AssertionError("Test-owned Relay worker did not stop before cleanup.")

    def test_two_instances_simultaneously_claim_one_plan_with_one_request(self):
        entered = self.gate()
        release = self.gate()
        start = threading.Barrier(3)

        def caller(*args, **kwargs):
            value = self.fake_caller(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Test response barrier timed out.")
            return value

        first = self.make_relay(caller=caller)
        second = self.make_relay(caller=caller)
        plan = first.plan(str(self.root), [self.task()])

        def submit(relay):
            start.wait(timeout=3)
            return relay.run(plan["plan_id"])

        a, a_outcome = self.launch(lambda: submit(first), "boundary-submit-a")
        b, b_outcome = self.launch(lambda: submit(second), "boundary-submit-b")
        start.wait(timeout=3)
        self.assertTrue(entered.wait(3))
        self.join(a)
        self.join(b)
        self.assertEqual(len(self.calls), 1)
        # A competing process may observe the lease before the durable claim.
        # It may report busy, but must never make another paid attempt.
        for kind, value in a_outcome + b_outcome:
            if kind == "error":
                self.assertIsInstance(value, RelayError)
                self.assertEqual(value.code, "run_busy")
        release.set()
        status = self.wait_terminal(first, plan["plan_id"])
        self.assertEqual(status["state"], "completed")
        first.run(plan["plan_id"])
        second.run(plan["plan_id"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(status["submission_attempts"], 1)

    def test_different_runs_share_one_active_batch_and_never_exceed_parallel_limit(self):
        entered = self.gate()
        release = self.gate()
        active = 0
        maximum = 0
        guard = threading.Lock()

        def caller(*args, **kwargs):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            try:
                value = self.fake_caller(*args, **kwargs)
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Test response barrier timed out.")
                return value
            finally:
                with guard:
                    active -= 1

        first = self.make_relay(caller=caller)
        second = self.make_relay(caller=caller)
        a = first.plan(str(self.root), [self.task()])
        b = second.plan(str(self.root), [self.task("two", "other.py")])
        first.run(a["plan_id"])
        self.assertTrue(entered.wait(3))
        with self.assertRaises(RelayError) as error:
            second.run(b["plan_id"])
        self.assertEqual(error.exception.code, "run_busy")
        self.assertEqual(len(self.calls), 1)
        release.set()
        self.assertEqual(self.wait_terminal(first, a["plan_id"])["state"], "completed")
        self.assertEqual(self.finish(second, b["plan_id"])["state"], "completed")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(maximum, 1)

    def test_terminated_claimed_process_is_never_resent_after_restart(self):
        plan = self.relay.plan(str(self.root), [self.task()])
        context = multiprocessing.get_context("spawn")
        dispatched = context.Event()
        process = context.Process(
            target=_interrupted_process,
            args=(self.config, str(self.state), plan["plan_id"], dispatched),
        )
        self.processes.append(process)
        process.start()
        self.assertTrue(dispatched.wait(6), "The child did not reach its synthetic dispatch.")
        process.terminate()
        process.join(timeout=6)
        self.assertFalse(process.is_alive())
        restarted = self.make_relay()
        before = restarted.job(plan["plan_id"])
        after = restarted.run(plan["plan_id"])
        restarted.run(plan["plan_id"])
        self.assertEqual(before["submission_attempts"], 1)
        self.assertEqual(after["submission_attempts"], 1)
        self.assertEqual(self.calls, [])
        self.assertIn("will not resend", after["observation"])
        # A dead process must not block unrelated new work forever.
        fresh = restarted.plan(str(self.root), [self.task()])
        restarted.run(fresh["plan_id"])
        self.assertEqual(self.wait_terminal(restarted, fresh["plan_id"])["state"], "completed")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(restarted.job(plan["plan_id"])["state"], "interrupted")

    def test_cancel_during_candidate_validation_publishes_no_candidate(self):
        entered = self.gate()
        release = self.gate()
        original = self.relay._candidate

        def paused_candidate(*args):
            value = original(*args)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Candidate barrier timed out.")
            return value

        plan = self.relay.plan(str(self.root), [self.task()])
        with patch.object(self.relay, "_candidate", side_effect=paused_candidate):
            self.relay.run(plan["plan_id"])
            self.assertTrue(entered.wait(3))
            self.relay.cancel(plan["plan_id"])
            release.set()
            status = self.wait_terminal(self.relay, plan["plan_id"])
        self.assertEqual(status["state"], "cancelled")
        self.assertEqual(status["tasks"][0]["state"], "cancelled_after_dispatch")
        self.assertEqual(status["tasks"][0]["usage"], USAGE)
        with self.assertRaises(RelayError) as error:
            self.relay.result(plan["plan_id"], "one")
        self.assertEqual(error.exception.code, "cancelled")
        self.assertFalse((self.state / plan["plan_id"] / "one.candidate.json").exists())
        self.assertEqual((self.root / "sample.py").read_text(), "answer = 1\n")

    def test_cancel_queued_task_after_first_dispatch_makes_no_second_request(self):
        entered = self.gate()
        release = self.gate()

        def caller(*args, **kwargs):
            value = self.fake_caller(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Dispatch barrier timed out.")
            return value

        config = {**self.config, "max_parallel": 2}
        relay = self.make_relay(config=config, caller=caller)
        plan = relay.plan(str(self.root), [
            self.task(), self.task("two", "other.py"),
        ])
        self.assertEqual(plan["dispatch_count"], 2)
        relay.run(plan["plan_id"])
        self.assertTrue(entered.wait(3))
        relay.cancel(plan["plan_id"])
        release.set()
        status = self.wait_terminal(relay, plan["plan_id"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(status["submission_attempts"], 1)
        self.assertCountEqual(
            [task["state"] for task in status["tasks"]],
            ["cancelled_after_dispatch", "cancelled_before_send"],
        )
        self.assertEqual(status["state"], "cancelled")

    def test_source_drift_before_run_rejects_without_dispatch(self):
        plan = self.relay.plan(str(self.root), [self.task()])
        (self.root / "sample.py").write_text("answer = 99\n", encoding="utf-8")
        with self.assertRaises(RelayError) as error:
            self.relay.run(plan["plan_id"])
        self.assertEqual(error.exception.code, "source_changed")
        self.assertEqual(self.calls, [])

    def test_configuration_drift_before_run_rejects_without_dispatch(self):
        source = self.base / "local-config.json"
        source.write_text(json.dumps(self.config), encoding="utf-8")
        relay = self.make_relay(source_config=source)
        plan = relay.plan(str(self.root), [self.task()])
        changed = copy.deepcopy(self.config)
        changed["providers"][0]["model"] = "different-exact-model"
        source.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(RelayError) as error:
            relay.run(plan["plan_id"])
        self.assertEqual(error.exception.code, "config_changed")
        self.assertEqual(self.calls, [])

    def test_source_drift_while_second_task_is_queued_blocks_its_dispatch(self):
        entered = self.gate()
        release = self.gate()

        def caller(*args, **kwargs):
            value = self.fake_caller(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Dispatch barrier timed out.")
            return value

        relay = self.make_relay(caller=caller)
        plan = relay.plan(str(self.root), [
            self.task(), self.task("two", "other.py"),
        ])
        relay.run(plan["plan_id"])
        self.assertTrue(entered.wait(3))
        (self.root / "other.py").write_text("answer = 99\n", encoding="utf-8")
        release.set()
        status = self.wait_terminal(relay, plan["plan_id"])
        self.assertEqual(len(self.calls), 1)
        second = next(task for task in status["tasks"] if task["id"] == "two")
        self.assertEqual(second["state"], "escalated")
        self.assertEqual(second["error_code"], "source_changed")

    def test_configuration_drift_while_second_task_is_queued_blocks_its_dispatch(self):
        source = self.base / "local-config.json"
        source.write_text(json.dumps(self.config), encoding="utf-8")
        entered = self.gate()
        release = self.gate()

        def caller(*args, **kwargs):
            value = self.fake_caller(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Dispatch barrier timed out.")
            return value

        relay = self.make_relay(caller=caller, source_config=source)
        plan = relay.plan(str(self.root), [self.task(), self.task("two", "other.py")])
        relay.run(plan["plan_id"])
        self.assertTrue(entered.wait(3))
        changed = copy.deepcopy(self.config)
        changed["providers"][0]["model"] = "different-exact-model"
        source.write_text(json.dumps(changed), encoding="utf-8")
        release.set()
        status = self.wait_terminal(relay, plan["plan_id"])
        self.assertEqual(len(self.calls), 1)
        second = next(task for task in status["tasks"] if task["id"] == "two")
        self.assertEqual(second["error_code"], "config_changed")

    def test_change_after_last_verification_still_sends_only_frozen_context(self):
        changed = self.gate()
        frozen_text = (self.root / "sample.py").read_bytes().decode("utf-8")

        def change_after_verify(root, snapshots):
            verify_snapshot(root, snapshots)
            if threading.current_thread().name.startswith("code-relay-worker"):
                (self.root / "sample.py").write_text("answer = 999\n", encoding="utf-8")
                changed.set()

        plan = self.relay.plan(str(self.root), [self.task()])
        with patch("code_relay.core.verify_snapshot", side_effect=change_after_verify):
            status = self.finish(self.relay, plan["plan_id"])
        self.assertTrue(changed.is_set())
        self.assertEqual(status["state"], "completed")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(
            self.calls[0]["payload"]["files"]["sample.py"]["content"], frozen_text
        )
        self.assertNotIn("answer = 999", self.calls[0]["user"])
        self.assertEqual((self.root / "sample.py").read_text(), "answer = 999\n")
        candidate = self.relay.result(plan["plan_id"], "one")
        self.assertFalse(candidate["source_still_matches"])
        self.assertIn("-answer = 1", candidate["diff"])

    def test_full_repeated_frozen_plan_exceeding_seven_mib_is_rejected_at_planning(self):
        inputs = ["context-a.txt", "context-b.txt", "context-c.txt"]
        for name in inputs:
            (self.root / name).write_text("x" * 60000, encoding="utf-8")
        config = copy.deepcopy(self.config)
        config["providers"][0]["input_limit_bytes"] = 262144
        config["max_requests_per_run"] = 64
        relay = self.make_relay(config=config)
        tasks = [
            self.task(
                task_id=f"task-{number}", read_files=inputs,
                write_files=[f"result-{number}.txt"],
            )
            for number in range(64)
        ]
        with self.assertRaises(RelayError) as error:
            relay.plan(str(self.root), tasks)
        self.assertEqual(error.exception.code, "input_limit")
        self.assertIn("7 MiB", str(error.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.state.glob("p-*")), [])

    def test_json_quoted_and_yaml_unquoted_secret_sources_are_blocked(self):
        sources = [
            '{"api_key": "synthetic-value-123456789"}\n',
            '{"access_token": "synthetic-value-123456789"}\n',
            'client_secret: synthetic-value-123456789\n',
            'password: synthetic-value-123456789\n',
            "'api-key': 'synthetic-value-123456789'\n",
        ]
        for content in sources:
            with self.subTest(format=content.split(":")[0]):
                (self.root / "sample.py").write_text(content, encoding="utf-8")
                with self.assertRaises(RelayError) as error:
                    self.relay.plan(str(self.root), [self.task()])
                self.assertEqual(error.exception.code, "sensitive_content")
                self.assertNotIn("synthetic-value-123456789", str(error.exception))
        self.assertEqual(self.calls, [])

    def test_traversal_reserved_names_and_case_aliases_are_rejected(self):
        for name in [
            "../outside.py", "x/../../outside.py", "/outside.py",
            "C:/outside.py", "sample.py:stream", "x\\outside.py",
            "x//sample.py", "./sample.py", "sample.py.", "sample.py ",
            "NUL.txt", "con", "SHORT~1.py",
        ]:
            with self.subTest(path=name):
                with self.assertRaises(RelayError) as error:
                    self.relay.plan(str(self.root), [self.task(read_files=[name])])
                self.assertEqual(error.exception.code, "unsafe_path")
        with self.assertRaises(RelayError) as error:
            self.relay.plan(str(self.root), [
                self.task(), self.task("two", "Sample.py"),
            ])
        self.assertEqual(error.exception.code, "unsafe_path")
        self.assertEqual(self.calls, [])

    def test_symlink_source_and_symlink_parent_are_rejected_when_supported(self):
        outside = self.base / "outside.py"
        outside.write_text("private = 123\n", encoding="utf-8")
        external = self.base / "external"
        external.mkdir()
        (external / "file.py").write_text("private = 123\n", encoding="utf-8")
        try:
            (self.root / "link.py").symlink_to(outside)
            (self.root / "linked").symlink_to(external, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Host cannot create test symlinks (errno={error.errno}).")
        for relative in ["link.py", "linked/file.py"]:
            with self.subTest(path=relative):
                with self.assertRaises(RelayError) as error:
                    self.relay.plan(str(self.root), [self.task(read_files=[relative])])
                self.assertEqual(error.exception.code, "unsafe_path")
        self.assertEqual(self.calls, [])

    def test_hardlinked_source_is_rejected_when_supported(self):
        try:
            os.link(self.root / "sample.py", self.root / "alias.py")
        except OSError as error:
            self.skipTest(f"Host cannot create test hard links (errno={error.errno}).")
        with self.assertRaises(RelayError) as error:
            self.relay.plan(str(self.root), [self.task()])
        self.assertEqual(error.exception.code, "unsafe_path")
        self.assertEqual(self.calls, [])

    def test_invalid_candidates_retain_actual_usage_without_exposing_outputs(self):
        cases = [
            ("malformed", "not a JSON candidate"),
            ("unapproved", json.dumps({
                "summary": "Changed", "files": [{"path": "other.py", "content": "value = 2\n"}],
            })),
            ("duplicate", json.dumps({
                "summary": "Changed", "files": [
                    {"path": "sample.py", "content": "answer = 2\n"},
                    {"path": "sample.py", "content": "answer = 3\n"},
                ],
            })),
            ("empty", json.dumps({"summary": "Cannot safely complete", "files": []})),
        ]
        for label, text in cases:
            with self.subTest(case=label):
                relay = self.make_relay(caller=lambda *args, text=text, **kwargs: response(text))
                plan = relay.plan(str(self.root), [self.task()])
                status = self.finish(relay, plan["plan_id"])
                self.assertEqual(status["state"], "needs_attention")
                row = status["tasks"][0]
                self.assertEqual(row["state"], "escalated")
                with self.assertRaises(RelayError) as error:
                    relay.result(plan["plan_id"], "one")
                self.assertEqual(error.exception.code, "no_candidate")
                self.assertEqual((self.root / "sample.py").read_text(), "answer = 1\n")
                self.assertEqual(row.get("usage"), USAGE)

    def test_duplicate_json_members_in_candidate_are_rejected(self):
        text = (
            '{"summary":"first","summary":"second",'
            '"files":[{"path":"sample.py","content":"answer = 2\\n"}]}'
        )
        relay = self.make_relay(caller=lambda *args, **kwargs: response(text))
        plan = relay.plan(str(self.root), [self.task()])
        status = self.finish(relay, plan["plan_id"])
        self.assertEqual(status["state"], "needs_attention")
        self.assertEqual(status["tasks"][0]["error_code"], "invalid_candidate")
        self.assertEqual(status["tasks"][0].get("usage"), USAGE)
        with self.assertRaises(RelayError):
            relay.result(plan["plan_id"], "one")

    def test_provider_failure_also_retains_actual_usage(self):
        def truncated(*args, **kwargs):
            raise ProviderError(
                "truncated", "Synthetic output reached the configured limit.",
                usage=USAGE,
            )

        relay = self.make_relay(caller=truncated)
        plan = relay.plan(str(self.root), [self.task()])
        status = self.finish(relay, plan["plan_id"])
        self.assertEqual(status["tasks"][0]["error_code"], "truncated")
        self.assertEqual(status["tasks"][0]["usage"], USAGE)
        self.assertEqual((self.root / "sample.py").read_text(), "answer = 1\n")


if __name__ == "__main__":
    unittest.main()
