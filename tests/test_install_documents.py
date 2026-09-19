"""Public installer behavior with isolated homes and a fake host command."""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from code_relay.common import RelayError
from code_relay.installer import install

ROOT = Path(__file__).resolve().parents[1]


class InstallDocumentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="code-relay-doc-install-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / "home"
        self.source = self.base / "package"
        self.source.mkdir()
        for path in [*ROOT.glob("*.md"), ROOT / "LICENSE"]:
            shutil.copyfile(path, self.source / path.name)
        for folder in [".codex-plugin", "code_relay", "skills", "docs", "governance", "templates", "verification"]:
            shutil.copytree(ROOT / folder, self.source / folder,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.calls = []
        locate = patch("code_relay.installer.shutil.which", return_value="synthetic-codex")
        locate.start()
        self.addCleanup(locate.stop)

    def runner(self, command, **kwargs):
        self.calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    def perform(self):
        return install(user_home=self.home, source=self.source, runner=self.runner)

    def test_frozen_install_includes_governance_and_preserves_user_data(self):
        data = self.home / "AppData/Local/CodeRelay/jobs"
        data.mkdir(parents=True)
        receipt = data / "budget.json"
        receipt.write_bytes(b'{"reserved": 7, "synthetic": true}')
        executable = self.base / "synthetic.exe"
        executable.write_bytes(b"Synthetic bundled executable")
        with patch("code_relay.installer.sys.frozen", True, create=True), patch(
                "code_relay.installer.sys.executable", str(executable)):
            result = self.perform()
        target = Path(result["source"])
        for name in ["AGENTS.md", "DEVELOPMENT_PRINCIPLES.md", "RUNTIME_LIFECYCLE.md",
                     "governance/OWNERSHIP.md", "docs/LIFECYCLE.md", "docs/OUTPUT_CONTRACTS.md"]:
            self.assertTrue((target / name).is_file(), name)
            self.assertEqual((target / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual(receipt.read_bytes(), b'{"reserved": 7, "synthetic": true}')
        self.assertEqual(self.calls[-1][1:], ["plugin", "add", "code-relay@personal", "--json"])

    def test_document_only_change_refreshes_source_install_version(self):
        first = self.perform()
        guide = self.source / "RUNTIME_LIFECYCLE.md"
        guide.write_bytes(guide.read_bytes() + b"\nSynthetic updated documentation.\n")
        second = self.perform()
        self.assertNotEqual(first["version"], second["version"])
        self.assertTrue(second["version"].startswith("0.1.1+codex."))
        self.assertEqual((Path(second["source"]) / "RUNTIME_LIFECYCLE.md").read_bytes(), guide.read_bytes())

    def test_missing_document_fails_before_installation_or_host_command(self):
        (self.source / "RUNTIME_LIFECYCLE.md").unlink()
        with self.assertRaises(RelayError) as caught:
            self.perform()
        self.assertEqual(caught.exception.code, "invalid_package")
        self.assertFalse((self.home / "plugins/code-relay").exists())
        self.assertEqual(self.calls, [])

    def test_repeat_install_does_not_rewrite_existing_marketplace(self):
        self.perform()
        market = self.home / ".agents/plugins/marketplace.json"
        market.write_text(json.dumps(json.loads(market.read_text()), indent=4) + "\n", encoding="utf-8")
        original = market.read_bytes()
        self.perform()
        self.assertEqual(market.read_bytes(), original)

    def test_existing_document_is_backed_up_before_replacement(self):
        first = self.perform()
        target = Path(first["source"])
        readme = target / "README.md"
        readme.write_bytes(b"Existing local document must remain recoverable.\n")
        second = self.perform()
        self.assertEqual((Path(second["backup"]) / "resources/README.md").read_bytes(),
                         b"Existing local document must remain recoverable.\n")
        self.assertEqual(readme.read_bytes(), (self.source / "README.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
