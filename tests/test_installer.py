import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from code_relay.common import RelayError
from code_relay.installer import install

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.calls = []
        self.locate = patch("code_relay.installer.shutil.which", return_value="codex.exe")
        self.locate.start()
        self.addCleanup(self.locate.stop)

    def runner(self, command, **kwargs):
        self.calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    def marketplace(self, entries=None):
        path = self.home / ".agents/plugins/marketplace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {"name": "existing", "interface": {"displayName": "My original plugins"},
                 "plugins": entries or [{"name": "unrelated", "source": {"source": "local", "path": "./plugins/unrelated"},
                                        "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"}, "category": "Productivity"}]}
        path.write_text(json.dumps(value))
        return path, value

    def test_repeat_install_preserves_other_plugins_and_versioned_runtime(self):
        market, original = self.marketplace()
        first = install(user_home=self.home, source=ROOT, runner=self.runner)
        second = install(user_home=self.home, source=ROOT, runner=self.runner)
        result = json.loads(market.read_text())
        self.assertEqual(result["interface"], original["interface"])
        self.assertEqual(result["plugins"][0], original["plugins"][0])
        self.assertEqual(len(result["plugins"]), 2)
        self.assertEqual(first["version"], second["version"])
        self.assertTrue(Path(second["backup"]).is_dir())
        self.assertEqual(self.calls[-1][1:], ["plugin", "add", "code-relay@existing", "--json"])
        config = json.loads((self.home / "plugins/code-relay/.mcp.json").read_text())
        command = config["mcpServers"]["code-relay"]
        smoke = subprocess.run([command["command"], *command["args"]], input=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
                               capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(smoke.returncode, 0)
        self.assertEqual(json.loads(smoke.stdout)["result"]["serverInfo"]["name"], "code-relay")

    def test_conflicting_source_is_not_overwritten(self):
        path, original = self.marketplace([{"name": "code-relay", "source": {"source": "local", "path": "./plugins/something-else"}}])
        with self.assertRaises(RelayError):
            install(user_home=self.home, source=ROOT, runner=self.runner)
        self.assertEqual(json.loads(path.read_text()), original)
        self.assertFalse(self.calls)

    def test_missing_codex_and_failed_host_install_are_not_success(self):
        with patch("code_relay.installer.shutil.which", return_value=None):
            with self.assertRaises(RelayError):
                install(user_home=self.home, source=ROOT, runner=self.runner)
        with self.assertRaises(RelayError):
            install(user_home=self.home, source=ROOT, runner=lambda *a, **k: SimpleNamespace(returncode=1))

    def test_frozen_install_copies_only_versioned_binary_and_metadata(self):
        executable = self.home / "test-bundle.exe"
        executable.write_bytes(b"synthetic-bundled-executable")
        with patch("code_relay.installer.sys.frozen", True, create=True), patch("code_relay.installer.sys.executable", str(executable)):
            result = install(user_home=self.home, source=ROOT, runner=self.runner)
        self.assertTrue(result["bundled_runtime"])
        self.assertEqual(Path(result["runtime"]).read_bytes(), executable.read_bytes())
        self.assertFalse((self.home / "plugins/code-relay/.git").exists())
        self.assertFalse((self.home / "plugins/code-relay/code_relay").exists())


if __name__ == "__main__":
    unittest.main()
