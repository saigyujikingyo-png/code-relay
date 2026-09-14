"""Explicit environment references and Windows user-scoped DPAPI secret storage."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from .common import RelayError, atomic_json, digest, read_json, require
from .config import data_home


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _protect(value: bytes, decrypt: bool = False) -> bytes:
    require(os.name == "nt", "credential_store", "Use an environment-variable key reference on this platform.")
    buffer = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    okay = function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    if not okay:
        raise RelayError("credential_store", "The user-scoped credential store could not be opened.")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(outgoing.data)


def _secret_path(provider: dict, directory: Path | None = None) -> Path:
    identity = [provider["protocol"], provider["base_url"], provider["key_env"]]
    return (directory or data_home() / "credentials") / (digest(identity) + ".dpapi")


def store_key(provider: dict, key: str, directory: Path | None = None) -> None:
    require(isinstance(key, str) and 1 <= len(key) <= 8192 and not any(c.isspace() for c in key),
            "invalid_key", "The API key must be nonempty and contain no whitespace.")
    import base64
    atomic_json(_secret_path(provider, directory), {"version": 1, "ciphertext": base64.b64encode(_protect(key.encode())).decode()})


def get_key(provider: dict, directory: Path | None = None) -> str:
    key = os.environ.get(provider["key_env"], "")
    if key:
        return key
    path = _secret_path(provider, directory)
    if path.exists() and os.name == "nt":
        import base64
        try:
            value = read_json(path, 65536)
            return _protect(base64.b64decode(value["ciphertext"], validate=True), decrypt=True).decode("utf-8")
        except (ValueError, KeyError, UnicodeError) as exc:
            raise RelayError("credential_store", "Stored credential is invalid; reconnect this endpoint.") from exc
    raise RelayError("missing_key", f"Connect the API credential for profile {provider['id']} in local setup.")


def has_key(provider: dict, directory: Path | None = None) -> bool:
    return bool(os.environ.get(provider["key_env"])) or (os.name == "nt" and _secret_path(provider, directory).is_file())
