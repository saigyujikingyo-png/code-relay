"""Explicit, bounded source export. No Git or shell is required at runtime."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata

from .common import RelayError, no_links, require

DENIED_PARTS = {".git", ".hg", ".svn", ".ssh", ".aws", ".azure", ".codex", ".agents",
                "node_modules", ".venv", "venv", ".code-relay", ".npm", ".pypirc"}
DENIED_NAMES = {"auth.json", "credentials.json", "credentials", ".netrc", ".npmrc",
                "id_rsa", "id_ed25519", "secrets.json"}
PROTECTED_PARTS = {"auth", "authentication", "authorization", "security", "migrations", "billing", "payments", ".github"}
PROTECTED_NAMES = {"agents.md", "development_principles.md", "package.json", "pyproject.toml",
                   "cargo.toml", "go.mod", "requirements.txt", "dockerfile", "makefile"}
SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".kdbx"}
SECRET_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|"
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b|"
    r"(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)[\"']?\s*[=:]\s*"
    r"(?:['\"][^'\"\n]{12,}['\"]|[A-Za-z0-9_./+=-]{12,})",
    re.IGNORECASE,
)


def safe_relative(value) -> str:
    require(isinstance(value, str) and 1 <= len(value) <= 240, "unsafe_path", "Use an explicit relative file path.")
    require(value == unicodedata.normalize("NFC", value) and not any(ord(c) < 32 for c in value),
            "unsafe_path", "File path contains unsupported characters.")
    require(not any(c in value for c in '\\:*?<>|"') and not value.startswith("/"),
            "unsafe_path", "File paths must use relative forward-slash notation.")
    parts = value.split("/")
    require(all(p and p not in {".", ".."} and not p.endswith((".", " ")) for p in parts),
            "unsafe_path", "File path traversal and aliases are not supported.")
    for part in parts:
        lower = part.lower()
        require(lower not in DENIED_PARTS and lower not in DENIED_NAMES and not lower.startswith(".env"),
                "sensitive_path", "Credential, runtime and agent-configuration paths cannot be exported.")
        stem = lower.split(".")[0]
        require(re.fullmatch(r"(con|prn|aux|nul|com[0-9]|lpt[0-9])", stem) is None and "~" not in part,
                "unsafe_path", "Reserved and short-name path aliases are not supported.")
    require(PurePosixPath(value).suffix.lower() not in SUFFIXES, "sensitive_path", "Credential files cannot be exported.")
    return value


def protected_write(value: str) -> bool:
    path = PurePosixPath(value.lower())
    return (bool(set(path.parts) & PROTECTED_PARTS) or path.name in PROTECTED_NAMES
            or path.name.endswith((".lock", "-lock.json", ".sh", ".ps1", ".bat", ".cmd"))
            or path.name.startswith(("test_auth", "test_security")))


def scan_text(content: str) -> None:
    require("\x00" not in content and SECRET_RE.search(content) is None,
            "sensitive_content", "Selected text contains a possible credential or unsupported binary content.")


def workspace_root(value: str, approved: list[str]) -> Path:
    require(isinstance(value, str) and Path(value).is_absolute(), "workspace_scope", "Choose an approved absolute workspace.")
    root = Path(value)
    no_links(root)
    require(root.is_dir(), "workspace_scope", "Workspace directory does not exist.")
    root = root.resolve()
    require(any(os.path.normcase(str(root)) == os.path.normcase(p) for p in approved),
            "workspace_scope", "This exact workspace root has not been granted in local setup.")
    return root


def capture(root: Path, relative: str, *, may_create: bool = False) -> dict:
    relative = safe_relative(relative)
    target = root.joinpath(*relative.split("/"))
    no_links(target)
    require(target.resolve().is_relative_to(root), "unsafe_path", "File is outside the approved workspace.")
    if not target.exists():
        require(may_create, "missing_file", "A selected context file does not exist.")
        return {"exists": False, "sha256": None, "content": ""}
    before = target.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "unsafe_path", "Only ordinary, unlinked files are supported.")
    require(before.st_size <= 65536, "input_limit", "A selected file exceeds 64 KiB; split the task.")
    with target.open("rb") as source:
        opened = os.fstat(source.fileno())
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                "source_changed", "Source changed during capture; replan.")
        raw = source.read(65537)
        after = os.fstat(source.fileno())
    no_links(target)
    current = target.stat()
    # On Windows/Python 3.13, stat can report creation time in st_ctime while
    # fstat reports change time. Compare ctime only between the same APIs.
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    require(signature(before) == signature(opened) == signature(after) == signature(current)
            and before.st_ctime_ns == current.st_ctime_ns and opened.st_ctime_ns == after.st_ctime_ns,
            "source_changed", "Source changed during capture; replan.")
    require(len(raw) <= 65536, "input_limit", "A selected file exceeds 64 KiB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise RelayError("unsupported_encoding", "Selected files must be UTF-8 text.") from exc
    scan_text(text)
    return {"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "content": text}


def verify_snapshot(root: Path, snapshots: dict) -> None:
    for path, frozen in snapshots.items():
        current = capture(root, path, may_create=not frozen["exists"])
        require(current["exists"] == frozen["exists"] and current["sha256"] == frozen["sha256"],
                "source_changed", "Source changed after planning; create a fresh plan.")
