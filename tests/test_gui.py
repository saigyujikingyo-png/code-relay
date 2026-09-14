"""Setup behavior uses temporary config and synthetic credential boundaries."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import platform
import tempfile
import time
import unittest
from unittest.mock import patch

from code_relay import config, credentials
from code_relay.common import RelayError
from code_relay.gui import ProfileEditor, SetupController, SetupWindow
from code_relay.providers import ProviderError


class SetupControllerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "settings" / "config.json"
        self.workspace = self.directory / "project"
        self.workspace.mkdir()
        self.controller = SetupController(self.path, windows=True)
        self.profile = {
            "id": "campus-worker", "protocol": "openai",
            "base_url": "https://models.example.test/api/v1",
            "model": "exact-model/Case:2026", "key_env": "RELAY_SYNTHETIC_KEY",
            "capabilities": ["tests", "docs"], "priority": 9,
            "concurrency": 1, "timeout_seconds": 35,
            "input_limit_bytes": 32000, "output_limit_tokens": 3000,
            "max_tokens_field": "max_completion_tokens",
        }

    def test_new_config_is_off_and_saves_arbitrary_exact_model(self):
        self.assertFalse(self.controller.load()["network_enabled"])
        saved = self.controller.save_profile(self.profile)
        self.assertEqual(saved["model"], "exact-model/Case:2026")
        self.assertEqual(saved["base_url"], self.profile["base_url"])
        self.assertFalse(config.load_config(self.path)["network_enabled"])

    def test_edit_preserves_other_profiles_settings_and_backup(self):
        self.controller.save_profile(self.profile)
        other = {**self.profile, "id": "second-worker", "model": "another/exact-id"}
        self.controller.save_profile(other)
        existing = self.controller.load()
        existing.update({"max_parallel": 4, "daily_request_limit": 19,
                         "max_requests_per_run": 7, "state_limit_mb": 56,
                         "network_enabled": True, "workspaces": [str(self.workspace)]})
        config.save_config(existing, self.path)
        before = copy.deepcopy(config.load_config(self.path))
        edited = {**before["providers"][0], "id": "renamed-worker", "priority": "3"}
        self.controller.save_profile(edited, original_id="campus-worker")
        after = config.load_config(self.path)
        self.assertEqual(after["providers"][1], before["providers"][1])
        for field in ("max_parallel", "daily_request_limit", "max_requests_per_run",
                      "state_limit_mb", "network_enabled", "workspaces"):
            self.assertEqual(after[field], before[field])
        self.assertEqual(after["providers"][0]["priority"], 3)
        self.assertEqual(config.load_config(self.path.with_suffix(".previous.json")), before)

    def test_duplicate_reuses_connection_without_copying_or_reading_secret(self):
        self.controller.save_profile(self.profile)
        with patch.object(credentials, "get_key", side_effect=AssertionError("must not decrypt")), \
                patch.object(credentials, "store_key") as store:
            duplicate = self.controller.duplicate_profile("campus-worker")
            self.assertEqual(duplicate["base_url"], self.profile["base_url"])
            self.assertEqual(duplicate["key_env"], self.profile["key_env"])
            self.assertEqual(duplicate["model"], "")
            self.assertNotEqual(duplicate["id"], self.profile["id"])
            self.assertEqual(len(self.controller.load()["providers"]), 1)
            duplicate.update(model="exact-qwen-id", priority="4")
            self.controller.save_profile(duplicate)
            store.assert_not_called()
        self.assertEqual(len(self.controller.load()["providers"]), 2)

    def test_duplicate_identifier_stays_valid_when_source_is_long(self):
        self.profile["id"] = "w" * 40
        self.controller.save_profile(self.profile)
        first = self.controller.duplicate_profile(self.profile["id"])
        first["model"] = "first-copy"
        self.controller.save_profile(first)
        second = self.controller.duplicate_profile(self.profile["id"])
        self.assertLessEqual(len(second["id"]), 40)
        self.assertNotEqual(first["id"], second["id"])

    def test_invalid_profile_never_stores_key_or_changes_config(self):
        self.controller.save_profile(self.profile)
        before = self.path.read_bytes()
        invalid = [
            {"model": "Model with spaces"}, {"priority": "1.5"},
            {"concurrency": "0"}, {"timeout_seconds": "121"},
            {"input_limit_bytes": "262145"}, {"output_limit_tokens": "16385"},
            {"capabilities": []}, {"base_url": "https://user:secret@example.test"},
            {"api_key": "synthetic-key"}, {"key_env": "INVALID-NAME"},
        ]
        with patch.object(credentials, "store_key") as store:
            for fields in invalid:
                with self.subTest(fields=fields), self.assertRaises((RelayError, ProviderError)):
                    self.controller.save_profile({**self.profile, **fields},
                                                 original_id=self.profile["id"], key="synthetic-key")
                self.assertEqual(self.path.read_bytes(), before)
            store.assert_not_called()

    def test_duplicate_or_missing_original_cannot_overwrite_another_profile(self):
        self.controller.save_profile(self.profile)
        with self.assertRaises(RelayError):
            self.controller.save_profile(self.profile)
        with self.assertRaises(RelayError):
            self.controller.save_profile(self.profile, original_id="not-present")
        self.controller.save_profile({**self.profile, "id": "second-worker"})
        with self.assertRaises(RelayError):
            self.controller.save_profile({**self.profile, "id": "second-worker"},
                                         original_id=self.profile["id"])

    def test_blank_key_preserves_existing_secret_and_nonblank_uses_store(self):
        with patch.object(credentials, "store_key") as store:
            self.controller.save_profile(self.profile, key="synthetic-test-key")
            self.assertEqual(store.call_count, 1)
            self.assertEqual(store.call_args.args[0]["key_env"], self.profile["key_env"])
            self.controller.save_profile({**self.profile, "priority": 10},
                                         original_id=self.profile["id"], key="")
            self.assertEqual(store.call_count, 1)
        self.assertNotIn("synthetic-test-key", self.path.read_text(encoding="utf-8"))
        self.assertNotIn("synthetic-test-key", self.path.with_suffix(".previous.json").read_text())

    def test_whitespace_key_rejected_without_storing_or_saving(self):
        with patch.object(credentials, "store_key") as store, self.assertRaises(RelayError):
            self.controller.save_profile(self.profile, key="   ")
        store.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_other_platform_requires_environment_reference(self):
        controller = SetupController(self.path, windows=False)
        with patch.object(credentials, "store_key") as store:
            with self.assertRaisesRegex(RelayError, "environment"):
                controller.save_profile(self.profile, key="synthetic-test-key")
            controller.save_profile(self.profile)
            store.assert_not_called()
        self.assertEqual(controller.load()["providers"][0]["key_env"], "RELAY_SYNTHETIC_KEY")

    def test_key_store_failure_is_sanitized_and_does_not_save_config(self):
        with patch.object(credentials, "store_key", side_effect=RuntimeError("synthetic-secret")):
            with self.assertRaises(RelayError) as caught:
                self.controller.save_profile(self.profile, key="synthetic-secret")
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertFalse(self.path.exists())

    def test_config_save_failure_after_key_storage_reports_partial_local_change(self):
        with patch.object(credentials, "store_key") as store, \
                patch.object(config, "save_config", side_effect=OSError("synthetic-secret")):
            with self.assertRaisesRegex(RelayError, "key was stored") as caught:
                self.controller.save_profile(self.profile, key="synthetic-secret")
        self.assertNotIn("synthetic-secret", str(caught.exception))
        store.assert_called_once()

    def test_workspace_grants_and_settings_preserve_fresh_configuration(self):
        self.controller.save_profile(self.profile)
        self.controller.add_workspace(str(self.workspace))
        self.controller.add_workspace(str(self.workspace))
        self.assertEqual(self.controller.load()["workspaces"], [str(self.workspace.resolve())])
        external = self.controller.load()
        external["state_limit_mb"] = 80
        config.save_config(external, self.path)
        self.controller.save_settings(network_enabled=True, max_parallel="3", daily_request_limit="15")
        actual = self.controller.load()
        self.assertEqual(actual["state_limit_mb"], 80)
        self.assertEqual(actual["providers"][0]["model"], self.profile["model"])
        self.assertEqual(actual["max_parallel"], 3)
        self.assertTrue(actual["network_enabled"])
        self.controller.remove_workspace(str(self.workspace.resolve()))
        self.assertEqual(self.controller.load()["workspaces"], [])
        with self.assertRaises(RelayError):
            self.controller.add_workspace("relative/path")
        with self.assertRaises(RelayError):
            self.controller.add_workspace(str(self.directory / "missing"))

    def test_invalid_global_settings_and_profile_removal(self):
        self.controller.save_profile(self.profile)
        for value in ({"network_enabled": "true"}, {"daily_request_limit": "0"},
                      {"max_parallel": "5"}, {"providers": []}):
            with self.subTest(value=value), self.assertRaises(RelayError):
                self.controller.save_settings(**value)
        self.controller.remove_profile(self.profile["id"])
        self.assertEqual(self.controller.load()["providers"], [])

    def test_config_path_follows_current_environment(self):
        controller = SetupController(windows=True)
        other_path = self.directory / "other.json"
        with patch.dict(os.environ, {"CODE_RELAY_CONFIG": str(self.path)}):
            self.assertEqual(controller.path, self.path)
            controller.save_profile(self.profile)
        with patch.dict(os.environ, {"CODE_RELAY_CONFIG": str(other_path)}):
            self.assertEqual(controller.path, other_path)
            self.assertEqual(controller.load()["providers"], [])
            controller.save_settings(network_enabled=False)
        self.assertTrue(other_path.exists())
        self.assertEqual(len(config.load_config(self.path)["providers"]), 1)

    def test_anthropic_profile_and_local_readiness_do_not_request_api(self):
        profile = {**self.profile, "protocol": "anthropic", "model": "user-exact-opus-id"}
        profile.pop("max_tokens_field")
        self.controller.save_profile(profile)
        with patch.object(credentials, "has_key", return_value=True), \
                patch.object(credentials, "get_key", side_effect=AssertionError("must not decrypt")), \
                patch("code_relay.providers.complete", side_effect=AssertionError("must not call")):
            rows = self.controller.profile_rows()
        self.assertEqual(len(rows[0]), 4)
        self.assertIn("unverified", rows[0][3])
        self.assertNotIn(profile["key_env"], json.dumps(rows))
        self.assertNotIn("max_tokens_field", self.controller.load()["providers"][0])


class SetupWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"GUI smoke platform: {platform.system()} {platform.release()}, Python {platform.python_version()}")
        try:
            import tkinter
        except ImportError:
            raise unittest.SkipTest("Tk runtime unavailable.") from None
        cls.tk = tkinter
        try:
            root = tkinter.Tk()
            root.withdraw()
            root.update_idletasks()
            root.destroy()
        except tkinter.TclError:
            # A headless machine is a separate gate, never a claimed GUI pass.
            raise unittest.SkipTest("Tk display unavailable.") from None

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.controller = SetupController(Path(temporary.name) / "config.json", windows=True)
        self.root = self.tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_hidden_window_constructs_and_key_entry_is_masked(self):
        window = SetupWindow(self.root, controller=self.controller)
        self.root.update_idletasks()
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertFalse(window.network_var.get())
        self.assertEqual(window.path_var.get(), str(self.controller.path))
        self.assertIn("unverified", window.status_var.get())
        editor = ProfileEditor(window, self.controller.new_profile(), show=False)
        self.addCleanup(editor.window.destroy)
        self.assertEqual(editor.window.state(), "withdrawn")
        self.assertEqual(editor.key_entry.cget("show"), "*")
        self.assertFalse(editor.secret_var.get())
        self.assertEqual(editor.fields["model"].get(), "")
        editor.fields["protocol"].set("Anthropic Messages")
        editor.update_protocol()
        self.assertEqual(str(editor.token_field.cget("state")), "disabled")

    def test_hidden_form_save_connects_exact_anthropic_profile(self):
        window = SetupWindow(self.root, controller=self.controller)
        editor = ProfileEditor(window, self.controller.new_profile(), show=False)
        editor.fields["id"].set("university-opus")
        editor.fields["protocol"].set("Anthropic Messages")
        editor.fields["base_url"].set("https://models.example.test/api")
        editor.fields["model"].set("Exact-User-Model:2026")
        editor.fields["key_env"].set("SYNTHETIC_SHARED_ELM_KEY")
        editor.fields["priority"].set("7")
        editor.secret_var.set("synthetic-not-a-real-key")
        with patch.object(credentials, "store_key") as store, \
                patch.object(credentials, "has_key", return_value=True), \
                patch.object(window.messagebox, "showerror", side_effect=AssertionError("unexpected UI error")), \
                patch("code_relay.providers.complete", side_effect=AssertionError("must not call")):
            editor.save()
        saved = self.controller.load()["providers"][0]
        self.assertEqual(saved["model"], "Exact-User-Model:2026")
        self.assertEqual(saved["protocol"], "anthropic")
        self.assertNotIn("max_tokens_field", saved)
        self.assertEqual(saved["priority"], 7)
        self.assertEqual(saved["key_env"], "SYNTHETIC_SHARED_ELM_KEY")
        self.assertEqual(window.models.selection(), ("university-opus",))
        self.assertEqual(editor.secret_var.get(), "")
        self.assertFalse(self.controller.load()["network_enabled"])
        store.assert_called_once()

    def test_other_platform_disables_api_key_entry(self):
        self.controller.windows = False
        window = SetupWindow(self.root, controller=self.controller)
        editor = ProfileEditor(window, self.controller.new_profile(), show=False)
        self.addCleanup(editor.window.destroy)
        self.assertEqual(str(editor.key_entry.cget("state")), "disabled")

    def test_install_is_injected_and_only_runs_when_invoked(self):
        calls = []

        def install():
            calls.append("called")
            return {"ok": True}

        window = SetupWindow(self.root, controller=self.controller, install_callback=install)
        self.assertEqual(calls, [])
        window.install()
        deadline = time.monotonic() + 3
        while window.installing and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertEqual(calls, ["called"])
        self.assertFalse(window.installing)
        self.assertIn("Restart Codex", window.status_var.get())

    def test_install_failure_does_not_display_arbitrary_callback_error(self):
        def install():
            raise RuntimeError("synthetic-private-token")

        window = SetupWindow(self.root, controller=self.controller, install_callback=install)
        window.install()
        deadline = time.monotonic() + 3
        while window.installing and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(window.installing)
        self.assertNotIn("synthetic-private-token", window.status_var.get())
        self.assertIn("failed", window.status_var.get())


if __name__ == "__main__":
    unittest.main()
