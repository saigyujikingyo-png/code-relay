"""Bounded, single-attempt transports for user-owned model APIs.

There is no account discovery, model aliasing, tool execution, streaming, retry,
or price estimation here. The scheduler owns per-provider concurrency; a fixed
transport ceiling also prevents unbounded workers when an OS resolver stalls.
Connections are direct (environment HTTP proxies are not consulted), use normal
certificate verification for HTTPS, and never follow redirects.

Protocol references:
https://developers.openai.com/api/reference/resources/chat
https://platform.claude.com/docs/en/api/messages/create
"""
from __future__ import annotations

import http.client
import json
import re
import socket
import ssl
import threading
import time
from urllib.parse import unquote, urlsplit, urlunsplit


_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_REQUEST_BYTES = 1024 * 1024
_NETWORK_SLOTS = threading.BoundedSemaphore(16)
_CAPABILITIES = ("tests", "docs", "boilerplate", "mechanical_edit")
_ALLOWED_KEYS = frozenset({
    "id", "protocol", "base_url", "model", "key_env", "concurrency",
    "timeout_seconds", "input_limit_bytes", "output_limit_tokens",
    "max_tokens_field", "priority", "capabilities", "allow_loopback_http", "enabled",
})


class ProviderError(Exception):
    """A sanitized failure; uncertainty never authorizes an automatic retry.

    usage contains reported token counts when a parseable response supplied them.
    A missing count is None, never an estimate or a presumed zero.
    """

    def __init__(
        self, code: str, message: str, *, uncertain: bool = False,
        usage: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain
        self.usage = dict(usage) if usage is not None else None


def _invalid(message: str) -> None:
    raise ProviderError("invalid_provider", message) from None


def _control(value: str) -> bool:
    return any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)


def _integer(raw: dict, field: str, default: int, minimum: int, maximum: int) -> int:
    value = raw.get(field, default)
    if type(value) is not int or not minimum <= value <= maximum:
        _invalid(f"{field} must be an integer from {minimum} to {maximum}.")
    return value


def _boolean(raw: dict, field: str, default: bool) -> bool:
    value = raw.get(field, default)
    if type(value) is not bool:
        _invalid(f"{field} must be a boolean.")
    return value


def _base_url(value: object, allow_loopback_http: bool) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > 2048
        or _control(value) or any(char.isspace() for char in value)
        or "\\" in value or "?" in value or "#" in value
        or _control(unquote(value)) or "\\" in unquote(value)
    ):
        _invalid("base_url must be a clean API base URL without query or fragment.")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
        if (
            not host or parts.username is not None or parts.password is not None
            or "@" in parts.netloc or "%" in host or not parts.netloc.isascii()
            or (port is not None and not 1 <= port <= 65535)
            or not parts.path.isascii()
        ):
            _invalid("base_url has an invalid host, port, credentials, or path.")
    except (ValueError, UnicodeError):
        _invalid("base_url has an invalid host or port.")
    if parts.scheme not in ("http", "https"):
        _invalid("base_url must use HTTPS.")
    if parts.scheme == "http" and not (
        allow_loopback_http and host in ("127.0.0.1", "::1", "localhost")
    ):
        _invalid("HTTP requires explicit permission and a literal loopback host.")
    # Preserve user-selected version/prefix paths; never invent or duplicate /v1.
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority += f":{port}"
    return urlunsplit((parts.scheme, authority, parts.path.rstrip("/"), "", ""))


def validate_provider(raw: dict) -> dict:
    """Return a fresh canonical profile. Secrets belong in key_env, never here."""
    if not isinstance(raw, dict):
        _invalid("Provider configuration must be an object.")
    if set(raw) - _ALLOWED_KEYS:
        _invalid("Provider configuration contains unsupported fields.")
    provider_id = raw.get("id")
    if not isinstance(provider_id, str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,39}", provider_id
    ):
        _invalid("id must be a lowercase slug of at most 40 characters.")
    protocol = raw.get("protocol")
    if protocol not in ("openai", "anthropic"):
        _invalid("protocol must be openai or anthropic.")
    model = raw.get("model")
    if (
        not isinstance(model, str) or not model or len(model) > 512
        or _control(model) or any(char.isspace() for char in model)
    ):
        _invalid("model must be the exact nonempty model ID, without whitespace.")
    try:
        model.encode("utf-8")
    except UnicodeError:
        _invalid("model must contain valid Unicode text.")
    key_env = raw.get(
        "key_env", "CODE_RELAY_" + provider_id.upper().replace("-", "_") + "_API_KEY"
    )
    if (
        not isinstance(key_env, str) or len(key_env) > 128
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env)
    ):
        _invalid("key_env must name an environment variable.")
    allow_http = _boolean(raw, "allow_loopback_http", False)
    capabilities = raw.get("capabilities", list(_CAPABILITIES))
    if (
        not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 4
        or any(not isinstance(item, str) or item not in _CAPABILITIES
               for item in capabilities)
        or len(set(capabilities)) != len(capabilities)
    ):
        _invalid("capabilities must contain distinct supported work categories.")
    result = {
        "id": provider_id, "protocol": protocol,
        "base_url": _base_url(raw.get("base_url"), allow_http),
        "model": model, "key_env": key_env,
        "concurrency": _integer(raw, "concurrency", 2, 1, 4),
        "timeout_seconds": _integer(raw, "timeout_seconds", 45, 1, 120),
        "input_limit_bytes": _integer(raw, "input_limit_bytes", 65536, 1, 262144),
        "output_limit_tokens": _integer(raw, "output_limit_tokens", 2048, 1, 16384),
        "priority": _integer(raw, "priority", 100, 0, 1000),
        "capabilities": list(capabilities),
        "allow_loopback_http": allow_http,
        "enabled": _boolean(raw, "enabled", True),
    }
    if protocol == "openai":
        field = raw.get("max_tokens_field", "max_tokens")
        if field not in ("max_tokens", "max_completion_tokens"):
            _invalid("max_tokens_field must be max_tokens or max_completion_tokens.")
        result["max_tokens_field"] = field
    elif "max_tokens_field" in raw:
        _invalid("max_tokens_field is supported only by the openai protocol.")
    return result


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _nested(raw: dict, name: str, key: str) -> object:
    child = raw.get(name)
    return child.get(key) if isinstance(child, dict) else None


def _usage(response: dict, protocol: str) -> dict:
    raw = response.get("usage")
    if not isinstance(raw, dict):
        raw = {}
    if protocol == "openai":
        values = (
            raw.get("prompt_tokens"), raw.get("completion_tokens"),
            _nested(raw, "prompt_tokens_details", "cached_tokens"),
            _nested(raw, "completion_tokens_details", "reasoning_tokens"),
        )
    else:
        # Anthropic reports cache reads separately from input_tokens. Preserve the
        # supplied quantities instead of pretending they have another meaning.
        values = (
            raw.get("input_tokens"), raw.get("output_tokens"),
            raw.get("cache_read_input_tokens"),
            _nested(raw, "output_tokens_details", "thinking_tokens"),
        )
    return dict(zip(
        ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens"),
        (_count(value) for value in values),
    ))


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member.")
        result[key] = value
    return result


def _no_constant(value: str) -> None:
    raise ValueError("Non-JSON numeric constant.")


def _parse_response(body: bytes, protocol: str) -> dict:
    try:
        response = json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_no_constant,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderError(
            "invalid_response", "Provider returned malformed JSON.", uncertain=True
        ) from None
    if not isinstance(response, dict):
        raise ProviderError(
            "invalid_response", "Provider returned an invalid response object.",
            uncertain=True,
        )
    usage = _usage(response, protocol)
    known_usage = usage if any(value is not None for value in usage.values()) else None

    def fail(code: str, message: str) -> None:
        raise ProviderError(code, message, usage=known_usage) from None

    if response.get("error") is not None:
        fail("invalid_response", "Provider returned an error in a success response.")
    if protocol == "openai":
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(
            choices[0], dict
        ):
            fail("invalid_response", "Provider must return exactly one completion.")
        choice = choices[0]
        finish = choice.get("finish_reason")
        if finish == "length":
            fail("truncated", "Provider output reached its limit and is incomplete.")
        if finish == "content_filter":
            fail("refused", "Provider declined the requested completion.")
        if finish in ("tool_calls", "function_call"):
            fail("tool_call", "Provider returned a tool call instead of text.")
        message = choice.get("message")
        if not isinstance(message, dict):
            fail("invalid_response", "Provider returned an invalid completion message.")
        if message.get("refusal") not in (None, ""):
            fail("refused", "Provider declined the requested completion.")
        if message.get("tool_calls") not in (None, []) or message.get(
            "function_call"
        ) is not None:
            fail("tool_call", "Provider returned a tool call instead of text.")
        if finish != "stop" or message.get("role") != "assistant":
            fail("invalid_response", "Provider did not return a completed assistant turn.")
        text = message.get("content")
    else:
        reason = response.get("stop_reason")
        details = response.get("stop_details")
        if reason in ("max_tokens", "model_context_window_exceeded"):
            fail("truncated", "Provider output reached its limit and is incomplete.")
        if reason == "refusal" or (
            isinstance(details, dict) and details.get("type") == "refusal"
        ):
            fail("refused", "Provider declined the requested completion.")
        if reason == "tool_use":
            fail("tool_call", "Provider returned a tool call instead of text.")
        if (
            reason != "end_turn" or response.get("role") != "assistant"
            or response.get("type") != "message"
        ):
            fail("invalid_response", "Provider did not return a completed assistant turn.")
        blocks = response.get("content")
        if not isinstance(blocks, list) or not blocks:
            fail("invalid_response", "Provider returned invalid content blocks.")
        parts = []
        for block in blocks:
            if not isinstance(block, dict):
                fail("invalid_response", "Provider returned an invalid content block.")
            kind = block.get("type")
            if kind in ("tool_use", "server_tool_use", "tool_result") or (
                isinstance(kind, str) and kind.endswith("_tool_result")
            ):
                fail("tool_call", "Provider returned tool content instead of text.")
            if kind == "refusal":
                fail("refused", "Provider declined the requested completion.")
            if kind in ("thinking", "redacted_thinking"):
                # Never return a reasoning trace as the code artifact.
                continue
            if kind != "text" or not isinstance(block.get("text"), str):
                fail("invalid_response", "Provider returned an unsupported content block.")
            parts.append(block["text"])
        text = "".join(parts)
    if not isinstance(text, str) or not text.strip():
        fail("invalid_response", "Provider returned no completed text.")
    try:
        text.encode("utf-8")
    except UnicodeError:
        fail("invalid_response", "Provider returned invalid Unicode text.")
    return {"text": text, "usage": usage, "outcome": "completed"}


class _Attempt:
    """State shared only by one caller and its bounded transport worker."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.finished = threading.Event()
        self.stop = threading.Event()
        self.socket: socket.socket | None = None
        self.sent = False
        self.abort_code = "cancelled"
        self.result: dict | None = None
        self.error: ProviderError | None = None

    def abort(self, code: str) -> bool:
        with self.lock:
            self.abort_code = code
            self.stop.set()
            uncertain = self.sent
            active_socket = self.socket
        # shutdown interrupts a blocked response read. Do not clear connection.sock:
        # HTTPConnection could otherwise reconnect and send after cancellation.
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                active_socket.close()
            except OSError:
                pass
        return uncertain

    def check(self, cancelled: threading.Event | None, deadline: float) -> None:
        if self.stop.is_set() or (cancelled is not None and cancelled.is_set()):
            code = self.abort_code if self.stop.is_set() else "cancelled"
            raise ProviderError(
                code, "Provider request was cancelled." if code == "cancelled"
                else "Provider request exceeded its total deadline.",
                uncertain=self.sent if code == "cancelled" else True,
            )
        if time.monotonic() >= deadline:
            raise ProviderError(
                "timeout", "Provider request exceeded its total deadline.",
                uncertain=True,
            )


def _read_body(response: http.client.HTTPResponse) -> bytes:
    raw_length = response.getheader("Content-Length")
    expected = None
    if raw_length is not None:
        if not re.fullmatch(r"[0-9]+", raw_length):
            raise ProviderError(
                "invalid_response", "Provider returned an invalid content length.",
                uncertain=True,
            )
        if len(raw_length) > 7 or int(raw_length) > _MAX_RESPONSE_BYTES:
            raise ProviderError(
                "response_too_large", "Provider response exceeds the one MiB limit.",
                uncertain=True,
            )
        expected = int(raw_length)
    encoding = response.getheader("Content-Encoding", "identity").strip().lower()
    if encoding != "identity":
        raise ProviderError(
            "invalid_response", "Provider returned an unsupported content encoding.",
            uncertain=True,
        )
    chunks = []
    size = 0
    while True:
        chunk = response.read(min(65536, _MAX_RESPONSE_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > _MAX_RESPONSE_BYTES:
            raise ProviderError(
                "response_too_large", "Provider response exceeds the one MiB limit.",
                uncertain=True,
            )
    if expected is not None and size != expected:
        raise http.client.IncompleteRead(b"")
    return b"".join(chunks)


def _perform(
    config: dict, api_key: str, payload: bytes, attempt: _Attempt,
    cancelled: threading.Event | None, deadline: float,
) -> None:
    connection = None
    response = None
    try:
        attempt.check(cancelled, deadline)
        base = urlsplit(config["base_url"])
        endpoint = "/chat/completions" if config["protocol"] == "openai" else "/messages"
        connection_type = (
            http.client.HTTPSConnection if base.scheme == "https"
            else http.client.HTTPConnection
        )
        kwargs = {"timeout": max(0.001, deadline - time.monotonic())}
        if base.scheme == "https":
            kwargs["context"] = ssl.create_default_context()
        connection = connection_type(base.hostname, base.port, **kwargs)
        # The caller's independent deadline includes DNS resolution and TLS.
        connection.connect()
        with attempt.lock:
            attempt.socket = connection.sock
            attempt.check(cancelled, deadline)
            attempt.sent = True
        headers = {
            "Content-Type": "application/json", "Accept": "application/json",
            "Accept-Encoding": "identity", "Connection": "close",
            "User-Agent": "Code-Relay",
        }
        if config["protocol"] == "openai":
            headers["Authorization"] = "Bearer " + api_key
        else:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        connection.request("POST", base.path + endpoint, body=payload, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ProviderError(
                "redirect", "Provider redirected the request; configure the final base URL."
            )
        if not 200 <= response.status < 300:
            raise ProviderError(
                f"http_{response.status}",
                f"Provider rejected the request with HTTP {response.status}.",
                uncertain=response.status == 408 or response.status >= 500,
            )
        body = _read_body(response)
        attempt.check(cancelled, deadline)
        attempt.result = _parse_response(body, config["protocol"])
    except ProviderError as error:
        attempt.error = error
    except (TimeoutError, socket.timeout):
        attempt.error = ProviderError(
            "timeout", "Provider request exceeded its network timeout.", uncertain=True
        )
    except Exception:
        # HTTP parser, TLS, DNS, socket and OS errors can contain URLs, credentials,
        # or provider bodies. None of those raw exceptions cross this boundary.
        attempt.error = ProviderError(
            "network_error", "Provider connection failed; the outcome may be unknown.",
            uncertain=True,
        )
    finally:
        if response is not None:
            try:
                response.close()
            except OSError:
                pass
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        _NETWORK_SLOTS.release()
        attempt.finished.set()


def complete(
    provider: dict, api_key: str, system: str, user: str, *,
    cancelled: threading.Event | None = None,
) -> dict:
    """Request one text completion, with a finite total wait and no retry.

    input_limit_bytes counts the combined UTF-8 prompts; the serialized request
    also has an absolute one MiB cap. Cancellation interrupts local waiting and
    closes the socket, but cannot promise to cancel provider work or billing.
    """
    started = time.monotonic()
    config = validate_provider(provider)
    if cancelled is not None and not isinstance(cancelled, threading.Event):
        raise ProviderError("invalid_request", "cancelled must be a threading Event.")
    if cancelled is not None and cancelled.is_set():
        raise ProviderError("cancelled", "Provider request was cancelled before sending.")
    if not config["enabled"]:
        raise ProviderError("disabled_provider", "This provider profile is disabled.")
    if (
        not isinstance(api_key, str) or not api_key or len(api_key) > 8192
        or any(ord(char) < 33 or ord(char) > 126 for char in api_key)
    ):
        raise ProviderError(
            "missing_api_key", "A valid API key is required through the configured credential."
        )
    if not isinstance(system, str) or not isinstance(user, str) or not user.strip():
        raise ProviderError("invalid_request", "Prompts must be text with a nonempty user prompt.")
    limit = config["input_limit_bytes"]
    if len(system) + len(user) > limit:
        raise ProviderError("input_limit", "Prompts exceed the configured UTF-8 input limit.")
    try:
        byte_count = len(system.encode("utf-8")) + len(user.encode("utf-8"))
    except UnicodeError:
        raise ProviderError("invalid_request", "Prompts must contain valid Unicode text.") from None
    if byte_count > limit:
        raise ProviderError("input_limit", "Prompts exceed the configured UTF-8 input limit.")
    request = {"model": config["model"], "stream": False}
    if config["protocol"] == "openai":
        request["messages"] = [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]
        request[config["max_tokens_field"]] = config["output_limit_tokens"]
    else:
        request["system"] = system
        request["messages"] = [{"role": "user", "content": user}]
        request["max_tokens"] = config["output_limit_tokens"]
    payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > _MAX_REQUEST_BYTES:
        raise ProviderError("input_limit", "Serialized request exceeds the one MiB limit.")
    if not _NETWORK_SLOTS.acquire(blocking=False):
        raise ProviderError(
            "transport_busy", "The bounded transport capacity is currently occupied."
        )
    attempt = _Attempt()
    deadline = started + config["timeout_seconds"]
    worker = threading.Thread(
        target=_perform, args=(config, api_key, payload, attempt, cancelled, deadline),
        daemon=True, name="code-relay-provider",
    )
    try:
        worker.start()
    except Exception:
        _NETWORK_SLOTS.release()
        raise ProviderError("transport_busy", "Provider transport could not start.") from None
    while not attempt.finished.wait(timeout=min(0.05, max(0, deadline - time.monotonic()))):
        if cancelled is not None and cancelled.is_set():
            uncertain = attempt.abort("cancelled")
            raise ProviderError(
                "cancelled", "Provider request was cancelled; remote work may continue."
                if uncertain else "Provider request was cancelled before sending.",
                uncertain=uncertain,
            )
        if time.monotonic() >= deadline:
            attempt.abort("timeout")
            raise ProviderError(
                "timeout", "Provider request exceeded its total deadline.", uncertain=True
            )
    if attempt.error is not None:
        raise attempt.error from None
    if attempt.result is None:
        raise ProviderError("network_error", "Provider returned no result.", uncertain=True)
    attempt.result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return attempt.result
