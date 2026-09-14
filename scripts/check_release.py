"""Public-source and package metadata checks using the standard library only."""
from pathlib import Path
import ast
import json
import re

ROOT = Path(__file__).resolve().parents[1]
required = [
    "AGENTS.md", "DEVELOPMENT_PRINCIPLES.md", "README.md", "LICENSE", "pyproject.toml",
    ".codex-plugin/plugin.json", ".mcp.json", "skills/code-relay/SKILL.md",
    "docs/ARCHITECTURE.md", "docs/INSTALL.md", "docs/COMPATIBILITY.md", "docs/PRIVACY.md",
    "scripts/setup_codex_cloud.sh",
]
for relative in required:
    assert (ROOT / relative).is_file(), f"Missing release entrypoint: {relative}"
manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
assert manifest["name"] == "code-relay" and manifest["version"] == "0.1.0"
assert manifest["license"] == "MIT" and manifest["mcpServers"] == "./.mcp.json"
assert manifest["skills"] == "./skills/"
assert "2026-09-13.2" in (ROOT / "DEVELOPMENT_PRINCIPLES.md").read_text(encoding="utf-8")
assert len(manifest["interface"]["defaultPrompt"]) <= 3
for code in [*ROOT.glob("code_relay/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob("tests/*.py")]:
    ast.parse(code.read_text(encoding="utf-8"), filename=str(code))
for folder in ["code_relay", "scripts", "skills", "docs", "tests", "verification"]:
    for path in (ROOT / folder).rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        assert path.suffix.lower() not in {".pem", ".key", ".dpapi"}, f"Private file: {path}"
        if path.suffix in {".py", ".md", ".json", ".sh", ".txt"}:
            text = path.read_text(encoding="utf-8")
            # Real-looking embedded tokens are forbidden; synthetic fixtures intentionally use other prefixes.
            assert re.search(r"sk-proj-[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{64,}", text) is None, f"Possible secret: {path}"
print("PASS: public entrypoints, plugin metadata, Python syntax and credential-pattern audit.")
print("Scope: source checks only; live providers, installed hosts and model quality are separate.")
