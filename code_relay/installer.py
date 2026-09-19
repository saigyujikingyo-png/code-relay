"""Conservative personal-plugin installation through the public Codex CLI."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from . import __version__
from .common import RelayError, atomic_bytes, atomic_json, no_links, private_dir, read_json, require


# Public install payload shared by the installer and frozen package builder.
INSTALL_FILES = (
    "skills/code-relay/SKILL.md", "LICENSE", "README.md", "AGENTS.md",
    "DEVELOPMENT_PRINCIPLES.md", "CLOUD_STORAGE.md", "RUNTIME_LIFECYCLE.md",
    "governance/OWNERSHIP.md", "governance/incidents/CB-2026-001.md",
    "templates/LIFECYCLE_RECORD.md", "docs/INSTALL.md", "docs/COMPATIBILITY.md",
    "docs/PRIVACY.md", "docs/ARCHITECTURE.md", "docs/OUTPUT_CONTRACTS.md",
    "docs/LIFECYCLE.md", "verification/2026-09-19-rules-adoption.md",
    "verification/2026-09-19-document-install.md",
    "verification/2026-09-14-preview-0.1.1.md", "verification/2026-09-14-preview.md",
)


def install_file(source: Path, destination: Path):
    no_links(source)
    no_links(destination)
    require(source.is_file(), "invalid_package", "A package file is missing or is not an ordinary file.")
    if destination.exists():
        require(destination.is_file() and destination.stat().st_nlink == 1, "target_conflict",
                "An installation destination is linked or is not an ordinary file.")
    atomic_bytes(destination, source.read_bytes())


def resources() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "plugin_resources"
    return Path(__file__).resolve().parents[1]


def install(*, user_home: Path | None = None, source: Path | None = None, runner=None) -> dict:
    user_home = (user_home or Path.home()).absolute()
    source = source or resources()
    runner = runner or subprocess.run
    codex = shutil.which("codex")
    require(codex is not None, "codex_missing", "Install or open Codex with its command line support, then try again.")
    target = user_home / "plugins" / "code-relay"
    market = user_home / ".agents" / "plugins" / "marketplace.json"
    no_links(target)
    no_links(market)
    if target.exists():
        require((target / ".codex-plugin/plugin.json").is_file()
                and read_json(target / ".codex-plugin/plugin.json").get("name") == "code-relay",
                "target_conflict", "The target folder is already used by another installation or local files.")
    manifest = read_json(source / ".codex-plugin" / "plugin.json")
    require(manifest.get("name") == "code-relay", "invalid_package", "This package has an unexpected plugin identity.")
    # Validate the complete public payload before changing an installation.
    for relative in INSTALL_FILES:
        origin = source / relative
        output = target / relative
        no_links(origin)
        no_links(output)
        require(origin.is_file(), "invalid_package", "A required installation document is missing.")
        if output.exists():
            require(output.is_file() and output.stat().st_nlink == 1,
                    "target_conflict", "An installation document destination is linked or not an ordinary file.")
    listing = read_json(market) if market.exists() else {
        "name": "personal", "interface": {"displayName": "Personal"}, "plugins": []}
    require(isinstance(listing, dict) and isinstance(listing.get("plugins"), list) and
            isinstance(listing.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_-]+", listing["name"]) is not None,
            "invalid_marketplace", "The existing personal marketplace needs repair before installation.")
    require(all(isinstance(p, dict) and isinstance(p.get("name"), str) for p in listing["plugins"])
            and len({p["name"] for p in listing["plugins"]}) == len(listing["plugins"]),
            "invalid_marketplace", "The existing marketplace has invalid or duplicate entries.")
    existing = next((p for p in listing["plugins"] if p.get("name") == "code-relay"), None)
    entry = {"name": "code-relay", "source": {"source": "local", "path": "./plugins/code-relay"},
             "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Developer Tools"}
    if existing:
        require(existing.get("source") == entry["source"], "marketplace_conflict",
                "A different source already owns the Code Relay marketplace entry.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = user_home / ".code-relay-install-backups" / stamp
    private_dir(target)
    # Preserve the previous metadata; old versioned runtimes remain usable for rollback.
    for previous in [market, target / ".mcp.json", target / ".codex-plugin" / "plugin.json"]:
        if previous.exists():
            private_dir(backup)
            no_links(previous)
            install_file(previous, backup / ("marketplace.json" if previous == market else previous.name))
    for relative in INSTALL_FILES:
        previous = target / relative
        if previous.exists():
            private_dir(backup / "resources" / Path(relative).parent)
            install_file(previous, backup / "resources" / relative)
    if getattr(sys, "frozen", False):
        binary = Path(sys.executable)
        full_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
        checksum = full_hash[:12]
        destination = private_dir(target / "bin") / f"code-relay-{__version__}-{checksum}.exe"
        no_links(destination)
        if destination.exists():
            require(destination.is_file() and destination.stat().st_nlink == 1
                    and hashlib.sha256(destination.read_bytes()).hexdigest() == full_hash,
                    "runtime_conflict", "An existing runtime fails integrity verification; restore it before installing.")
        else:
            install_file(binary, destination)
        command = str(destination)
        arguments = ["serve"]
    else:
        destination = private_dir(target / "runtime" / __version__)
        for file in (source / "code_relay").glob("*.py"):
            no_links(file)
            folder = private_dir(destination / "code_relay")
            install_file(file, folder / file.name)
        command = sys.executable
        arguments = ["-c", "import sys,runpy; sys.path.insert(0," + repr(str(destination)) +
                     "); sys.argv=['code-relay','serve']; runpy.run_module('code_relay',run_name='__main__')"]
        inputs = [*(source / "code_relay").glob("*.py"),
                  source / ".codex-plugin/plugin.json", *(source / name for name in INSTALL_FILES)]
        content = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in inputs}
        checksum = hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    # Content-based version suffix refreshes the host cache without changing product version.
    manifest["version"] = __version__ + "+codex." + checksum
    atomic_json(target / ".codex-plugin" / "plugin.json", manifest)
    atomic_json(target / ".mcp.json", {"mcpServers": {"code-relay": {"command": command, "args": arguments}}})
    for relative in INSTALL_FILES:
        origin = source / relative
        no_links(origin)
        output = target / relative
        private_dir(output.parent)
        no_links(output)
        install_file(origin, output)
    if not existing:
        listing["plugins"].append(entry)
        atomic_json(market, listing)
    # An existing entry already points at this source. Do not rewrite another
    # installer's concurrent marketplace changes or user formatting on update.
    kwargs = {"capture_output": True, "text": True, "timeout": 45}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        response = runner([codex, "plugin", "add", f"code-relay@{listing['name']}", "--json"], **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RelayError("host_install_uncertain", "Codex installation did not return a confirmed result. Inspect the Plugins panel before retrying.") from exc
    require(response.returncode == 0, "host_install_failed",
            "Plugin files are prepared, but Codex did not confirm installation. Check the Plugins panel.")
    return {"installed": True, "plugin": "code-relay", "version": manifest["version"],
            "source": str(target), "marketplace": str(market), "backup": str(backup) if backup.exists() else None,
            "runtime": command, "bundled_runtime": bool(getattr(sys, "frozen", False)),
            "next_step": "Open a new Codex task to pick up Code Relay, then configure API models locally.",
            "host_model_acceptance": "unverified"}
