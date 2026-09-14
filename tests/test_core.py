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
from code_relay.core import Relay


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        (self.root / "sample.py").write_text("answer = 1\n", encoding="utf-8")
        self.state = Path(self.temp.name) / "state"
        self.config = validate_config({
            "workspaces": [str(self.root)],
            "network_enabled": True,
            "providers": [{"id": "worker", "protocol": "openai", "base_url": "https://api.example.com/v1",
                           "model": "user-exact-model", "key_env": "RELAY_TEST_KEY"}],
        })
        self.environment = patch.dict(os.environ, {"RELAY_TEST_KEY": "synthetic-test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.calls = []
        self.relay = Relay(self.config, state_dir=self.state, caller=self.complete)

    def task(self, **changes):
        return {"id": "one", "instruction": "Change the numeric fixture to two.",
                "kind": "mechanical_edit", "risk": "low", "complexity": 1,
                "read_files": ["sample.py"], "write_files": ["sample.py"],
                "acceptance": ["The fixture value equals 2."], **changes}

    def complete(self, provider, key, system, user, *, cancelled=None):
        self.calls.append(json.loads(user))
        return {"text": json.dumps({"summary": "Updated numeric fixture.",
                    "files": [{"path": "sample.py", "content": "answer = 2\n"}]}),
                "usage": {"input_tokens": 10, "output_tokens": 12, "cached_input_tokens": None,
                          "reasoning_tokens": None}, "elapsed_ms": 1, "outcome": "completed"}

    def finish(self, relay, plan_id):
        relay.run(plan_id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = relay.job(plan_id)
            if status["state"] not in {"queued", "running", "cancelling"}:
                return status
            time.sleep(0.01)
        self.fail("Job failed to terminate.")

    def test_candidate_does_not_modify_source_and_run_is_idempotent(self):
        plan = self.relay.plan(str(self.root), [self.task()])
        self.assertEqual(plan["dispatch_count"], 1)
        result = self.finish(self.relay, plan["plan_id"])
        self.assertEqual(result["state"], "completed")
        self.relay.run(plan["plan_id"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.root / "sample.py").read_text(), "answer = 1\n")
        candidate = self.relay.result(plan["plan_id"], "one")
        self.assertIn("+answer = 2", candidate["diff"])
        self.assertEqual(candidate["disposition"], "needs_host_review")

    def test_changed_input_prevents_network(self):
        plan = self.relay.plan(str(self.root), [self.task()])
        (self.root / "sample.py").write_text("answer = 99\n")
        with self.assertRaisesRegex(RelayError, "changed"):
            self.relay.run(plan["plan_id"])
        self.assertEqual(self.calls, [])

    def test_advanced_and_ambiguous_work_stays_with_host(self):
        for fields in [{"kind": "architecture"}, {"risk": "high"}, {"complexity": 3},
                       {"instruction": "Change OAuth token verification."},
                       {"acceptance": []}, {"depends_on": ["upstream"]}]:
            with self.subTest(fields=fields):
                plan = self.relay.plan(str(self.root), [self.task(**fields)])
                self.assertEqual(plan["dispatch_count"], 0)

    def test_read_write_conflicts_stay_with_host(self):
        (self.root / "other.py").write_text("value = 0\n")
        plan = self.relay.plan(str(self.root), [self.task(),
            self.task(id="two", write_files=["other.py"])])
        self.assertEqual(plan["dispatch_count"], 0)

    def test_secret_and_traversal_never_export(self):
        for name in [".env", "../outside.py", "x/../../outside.py", "C:/secret.py", "sample.py:secret"]:
            with self.subTest(name=name):
                with self.assertRaises(RelayError):
                    self.relay.plan(str(self.root), [self.task(read_files=[name])])
        (self.root / "sample.py").write_text('api_key = "sk-abcdefghijklmnopqrstuvwxyz0123456789"')
        with self.assertRaises(RelayError):
            self.relay.plan(str(self.root), [self.task()])
        self.assertFalse(self.calls)

    def test_unknown_output_file_is_rejected(self):
        def bad(*args, **kwargs):
            result = self.complete(*args, **kwargs)
            result["text"] = json.dumps({"summary": "Changed", "files": [{"path": "../escape.py", "content": "oops"}]})
            return result
        self.relay.caller = bad
        plan = self.relay.plan(str(self.root), [self.task()])
        result = self.finish(self.relay, plan["plan_id"])
        self.assertEqual(result["tasks"][0]["state"], "escalated")
        self.assertFalse((Path(self.temp.name) / "escape.py").exists())

    def test_missing_key_and_budget_do_not_call(self):
        with patch.dict(os.environ, {"RELAY_TEST_KEY": ""}):
            plan = self.relay.plan(str(self.root), [self.task()])
            with self.assertRaises(RelayError):
                self.relay.run(plan["plan_id"])
        restricted = {**self.config, "daily_request_limit": 1}
        relay = Relay(restricted, state_dir=self.state, caller=self.complete)
        self.finish(relay, relay.plan(str(self.root), [self.task()])["plan_id"])
        new_plan = relay.plan(str(self.root), [self.task()])
        with self.assertRaisesRegex(RelayError, "daily"):
            relay.run(new_plan["plan_id"])
        self.assertEqual(len(self.calls), 1)

    def test_restart_never_repeats_a_run(self):
        plan = self.relay.plan(str(self.root), [self.task()])
        self.finish(self.relay, plan["plan_id"])
        restarted = Relay(self.config, state_dir=self.state, caller=self.complete)
        restarted.run(plan["plan_id"])
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
