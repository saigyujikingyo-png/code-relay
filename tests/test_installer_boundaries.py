"""Installer regression boundaries using synthetic files and a fake Codex runner.

These tests never install in the current user's home or execute a Codex command.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from code_relay import __version__
from code_relay.common import RelayError
from code_relay.installer import INSTALL_FILES, install


class InstallerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="code-relay-installer-boundary-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.home = self.base / "synthetic-home"
        self.source = self.base / "synthetic-package"
        for relative in [".codex-plugin", "skills/code-relay", "code_relay"]:
            (self.source / relative).mkdir(parents=True, exist_ok=True)
        (self.source / ".codex-plugin/plugin.json").write_text(
            json.dumps({"name": "code-relay", "version": __version__}), encoding="utf-8")
        for relative in INSTALL_FILES:
            (self.source / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.source / relative).write_text("Synthetic package resource.\n", encoding="utf-8")
        (self.source / "code_relay/core.py").write_text(
            "SYNTHETIC_PACKAGE_CODE = True\n", encoding="utf-8")
        self.calls = []
        locate = patch("code_relay.installer.shutil.which", return_value="synthetic-codex")
        locate.start()
        self.addCleanup(locate.stop)

    def runner(self, command, **kwargs):
        self.calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    def install(self, home=None):
        return install(user_home=home or self.home, source=self.source, runner=self.runner)

    @staticmethod
    def snapshot(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
                for path in root.rglob("*")}

    def test_existing_source_runtime_hardlink_does_not_overwrite_external_file(self):
        self.install()
        target = self.home / "plugins/code-relay"
        destination = target / "runtime" / __version__ / "code_relay/core.py"
        self.assertTrue(destination.is_file())
        destination.unlink()
        external = self.base / "unrelated-user-file.txt"
        original = b"Unrelated user content must survive installation.\n"
        external.write_bytes(original)
        try:
            os.link(external, destination)
        except OSError as exc:
            self.skipTest(f"Hard links are unavailable for this temporary filesystem: {exc}")
        self.assertEqual(destination.stat().st_nlink, 2)
        marketplace = self.home / ".agents/plugins/marketplace.json"
        previous_marketplace = marketplace.read_bytes()
        previous_mcp = (target / ".mcp.json").read_bytes()
        self.calls.clear()

        with self.assertRaises(RelayError) as error:
            self.install()

        self.assertEqual(error.exception.code, "target_conflict")
        self.assertEqual(external.read_bytes(), original)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(marketplace.read_bytes(), previous_marketplace)
        self.assertEqual((target / ".mcp.json").read_bytes(), previous_mcp)
        self.assertEqual(self.calls, [])

    def test_corrupt_existing_checksum_named_binary_is_not_reused(self):
        executable = self.base / "synthetic-package.exe"
        executable.write_bytes(b"Synthetic original bundled executable.\n")
        with patch("code_relay.installer.sys.frozen", True, create=True), patch(
                "code_relay.installer.sys.executable", str(executable)):
            result = self.install()
            runtime = Path(result["runtime"])
            self.assertEqual(runtime.read_bytes(), executable.read_bytes())
            replacement = b"Unexpected existing executable content.\n"
            runtime.write_bytes(replacement)
            self.assertNotEqual(runtime.read_bytes(), executable.read_bytes())
            target = self.home / "plugins/code-relay"
            marketplace = self.home / ".agents/plugins/marketplace.json"
            previous_marketplace = marketplace.read_bytes()
            previous_mcp = (target / ".mcp.json").read_bytes()
            self.calls.clear()

            with self.assertRaises(RelayError) as error:
                self.install()

        self.assertEqual(error.exception.code, "runtime_conflict")
        self.assertEqual(runtime.read_bytes(), replacement)
        self.assertEqual(marketplace.read_bytes(), previous_marketplace)
        self.assertEqual((target / ".mcp.json").read_bytes(), previous_mcp)
        self.assertEqual(self.calls, [])

    def test_unowned_existing_destination_is_not_modified(self):
        for owner in [None, "unrelated-plugin"]:
            with self.subTest(existing_owner=owner):
                home = self.base / ("missing-owner-home" if owner is None else "other-owner-home")
                target = home / "plugins/code-relay"
                target.mkdir(parents=True)
                (target / "README.md").write_bytes(b"Existing user's unrelated files.\n")
                (target / ".mcp.json").write_bytes(b"Existing user's configuration.\n")
                if owner is not None:
                    (target / ".codex-plugin").mkdir()
                    (target / ".codex-plugin/plugin.json").write_text(
                        json.dumps({"name": owner, "version": "1.0.0"}), encoding="utf-8")
                marketplace = home / ".agents/plugins/marketplace.json"
                marketplace.parent.mkdir(parents=True)
                marketplace.write_text(json.dumps({"name": "personal", "plugins": [
                    {"name": "unrelated-plugin", "source": {"source": "local", "path": "./plugins/unrelated"}}
                ]}), encoding="utf-8")
                before = self.snapshot(home)

                with self.assertRaises(RelayError) as error:
                    self.install(home)

                self.assertEqual(error.exception.code, "target_conflict")
                self.assertEqual(self.snapshot(home), before)
                self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
