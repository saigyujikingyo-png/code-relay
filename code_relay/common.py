"""Small shared validation and private-file primitives."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time


class RelayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise RelayError(code, message)


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def no_links(path: Path) -> None:
    for entry in [path, *path.parents]:
        require(not is_link(entry), "unsafe_path", "Symbolic links and reparse points are not supported.")


def private_dir(path: Path) -> Path:
    path = path.absolute()
    no_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def atomic_json(path: Path, value) -> None:
    atomic_bytes(path, json_bytes(value))


def atomic_bytes(path: Path, value: bytes) -> None:
    private_dir(path.parent)
    no_links(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        # Windows readers and antivirus scanners can briefly deny rename sharing.
        # Retrying this local atomic replace cannot repeat an external request.
        for attempt in range(25):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 24:
                    raise
                time.sleep(0.01)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path, limit: int = 8 * 1024 * 1024):
    no_links(path)
    for attempt in range(25):
        try:
            with path.open("rb") as source:
                data = source.read(limit + 1)
            break
        except PermissionError:
            if attempt == 24:
                raise
            time.sleep(0.01)
    require(len(data) <= limit, "size_limit", "Local record exceeds the size limit.")
    try:
        return strict_json(data)
    except (ValueError, UnicodeError) as exc:
        raise RelayError("invalid_record", "Local JSON record is invalid.") from exc


def strict_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON member.")
            result[key] = item
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite JSON value.")

    return json.loads(value, object_pairs_hook=unique, parse_constant=invalid_constant)


def identifier(value, label: str = "identifier") -> str:
    require(isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,39}", value) is not None,
            "invalid_argument", f"Invalid {label}; use a short lowercase identifier.")
    return value


def integer(value, minimum: int, maximum: int, label: str) -> int:
    require(type(value) is int and minimum <= value <= maximum,
            "invalid_argument", f"{label} must be an integer between {minimum} and {maximum}.")
    return value
