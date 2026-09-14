"""Explicit local configuration; credentials are never accepted in public config."""
from __future__ import annotations

import os
from pathlib import Path

from .common import RelayError, atomic_json, integer, no_links, read_json, require
from .providers import validate_provider

DEFAULTS = {
    "version": 1, "providers": [], "workspaces": [], "network_enabled": False,
    "max_parallel": 2, "max_requests_per_run": 12, "daily_request_limit": 40,
    "state_limit_mb": 128,
}


def data_home() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "CodeRelay"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "code-relay"


def config_path() -> Path:
    override = os.environ.get("CODE_RELAY_CONFIG")
    return Path(override).expanduser().absolute() if override else data_home() / "config.json"


def validate_config(raw: dict) -> dict:
    require(isinstance(raw, dict) and set(raw) <= set(DEFAULTS), "invalid_config", "Unknown configuration fields.")
    result = {**DEFAULTS, **raw}
    require(type(result["version"]) is int and result["version"] == 1, "invalid_config", "Unsupported configuration version.")
    require(type(result["network_enabled"]) is bool, "invalid_config", "network_enabled must be a boolean.")
    require(isinstance(result["providers"], list) and len(result["providers"]) <= 32, "invalid_config", "Configure at most 32 model profiles.")
    result["providers"] = [validate_provider(p) for p in result["providers"]]
    ids = [p["id"] for p in result["providers"]]
    require(len(ids) == len(set(ids)), "invalid_config", "Model profile identifiers must be unique.")
    roots = result["workspaces"]
    require(isinstance(roots, list) and len(roots) <= 32, "invalid_config", "Configure at most 32 workspace roots.")
    normalised = []
    for raw_root in roots:
        require(isinstance(raw_root, str) and Path(raw_root).is_absolute(), "invalid_config", "Workspace roots must be absolute.")
        root = Path(raw_root)
        no_links(root)
        require(root.is_dir(), "invalid_config", "A configured workspace directory does not exist.")
        normalised.append(str(root.resolve()))
    result["workspaces"] = sorted(set(normalised))
    for name, low, high in [("max_parallel", 1, 4), ("max_requests_per_run", 1, 64),
                            ("daily_request_limit", 1, 10000), ("state_limit_mb", 8, 1024)]:
        result[name] = integer(result[name], low, high, name)
    return result


def load_config(path: Path | None = None) -> dict:
    path = path or config_path()
    return validate_config(read_json(path)) if path.exists() else validate_config({})


def save_config(value: dict, path: Path | None = None) -> dict:
    clean = validate_config(value)
    path = path or config_path()
    if path.exists():
        atomic_json(path.with_suffix(".previous.json"), read_json(path))
    atomic_json(path, clean)
    return clean
