"""Synthetic loopback acceptance for provider transports. No real API calls."""
from __future__ import annotations

import copy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
import unittest

from code_relay.providers import ProviderError, complete, validate_provider


SECRET = "synthetic-provider-secret"


def openai_response(text="def add(a, b):\n    return a + b\n", **overrides):
    result = {
        "choices": [
            {"index": 0, "finish_reason": "stop",
             "message": {"role": "assistant", "content": text}}
        ],
        "usage": {
            "prompt_tokens": 31, "completion_tokens": 12,
            "prompt_tokens_details": {"cached_tokens": 7},
            "completion_tokens_details": {"reasoning_tokens": 3},
        },
    }
    result.update(overrides)
    return result


def anthropic_response():
    return {
        "type": "message", "role": "assistant", "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": "first\n"},
            {"type": "text", "text": "second"},
        ],
        "usage": {
            "input_tokens": 31, "output_tokens": 12,
            "cache_read_input_tokens": 7,
            "output_tokens_details": {"thinking_tokens": 3},
        },
    }


def send_response(handler, body, status=200, headers=None):
    if isinstance(body, dict):
        body = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
    if not headers or "Content-Length" not in headers:
        handler.send_header("Content-Length", str(len(body)))
    if not headers or "Content-Type" not in headers:
        handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(body)
    handler.wfile.flush()


@contextmanager
def endpoint(responder=None):
    requests = []
    received = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                self.connection.settimeout(3)
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                requests.append({
                    "path": self.path, "headers": dict(self.headers),
                    "raw": raw, "body": json.loads(raw),
                })
                received.set()
                if responder is None:
                    send_response(self, openai_response())
                else:
                    responder(self, release)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.block_on_close = False
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    worker.start()
    try:
        yield {
            "url": f"http://127.0.0.1:{server.server_port}/v1",
            "requests": requests, "received": received, "release": release,
        }
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def profile(base_url="https://example.invalid/v1", **overrides):
    raw = {
        "id": "worker-one", "protocol": "openai",
        "base_url": base_url, "model": "exact-user-model",
    }
    if isinstance(base_url, str) and base_url.startswith("http://"):
        raw["allow_loopback_http"] = True
    raw.update(overrides)
    return raw


class ProviderConfigurationTests(unittest.TestCase):
    def invalid(self, raw):
        with self.assertRaises(ProviderError) as error:
            validate_provider(raw)
        self.assertEqual(error.exception.code, "invalid_provider")
        self.assertFalse(error.exception.uncertain)
        return error.exception

    def test_defaults_are_canonical_and_do_not_modify_input(self):
        original = profile()
        snapshot = copy.deepcopy(original)
        config = validate_provider(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(config["key_env"], "CODE_RELAY_WORKER_ONE_API_KEY")
        self.assertEqual(config["concurrency"], 2)
        self.assertEqual(config["timeout_seconds"], 45)
        self.assertEqual(config["input_limit_bytes"], 65536)
        self.assertEqual(config["output_limit_tokens"], 2048)
        self.assertEqual(config["priority"], 100)
        self.assertEqual(config["max_tokens_field"], "max_tokens")
        self.assertEqual(config["capabilities"],
                         ["tests", "docs", "boilerplate", "mechanical_edit"])
        self.assertTrue(config["enabled"])
        self.assertFalse(config["allow_loopback_http"])
        self.assertEqual(validate_provider(config), config)

    def test_exact_models_and_shared_endpoint_credentials(self):
        configs = [validate_provider(profile(
            model=model, key_env="MY_ELM_KEY", base_url="https://example.invalid/api/v1/"
        )) for model in ["provider/OPUS-exact", "SOL-exact", "TERRA-exact", "QWEN-exact"]]
        self.assertEqual([item["model"] for item in configs],
                         ["provider/OPUS-exact", "SOL-exact", "TERRA-exact", "QWEN-exact"])
        self.assertEqual(configs[0]["base_url"], "https://example.invalid/api/v1")

    def test_anthropic_has_no_openai_token_parameter(self):
        config = validate_provider(profile(protocol="anthropic"))
        self.assertNotIn("max_tokens_field", config)
        self.assertEqual(validate_provider(config), config)
        self.invalid(profile(protocol="anthropic", max_tokens_field="max_tokens"))

    def test_unknown_keys_missing_fields_and_bad_shapes_are_rejected(self):
        for raw in [
            None, [], {}, profile(api_key=SECRET), profile(extra=SECRET),
            profile(id="Bad_Name"), profile(id="a" * 41), profile(id=7),
            profile(protocol="gemini"), profile(protocol=[]),
            profile(model=""), profile(model=None),
            profile(model="model\ninjection"), profile(key_env="MY-KEY"),
            profile(key_env=SECRET + "\n"), profile(key_env=""),
            profile(base_url=1),
        ]:
            with self.subTest(raw_type=type(raw).__name__):
                error = self.invalid(raw)
                self.assertNotIn(SECRET, str(error))

    def test_strict_numeric_and_boolean_limits(self):
        bounds = {
            "concurrency": (1, 4), "timeout_seconds": (1, 120),
            "input_limit_bytes": (1, 262144), "output_limit_tokens": (1, 16384),
            "priority": (0, 1000),
        }
        for field, (minimum, maximum) in bounds.items():
            for value in [minimum - 1, maximum + 1, True, "2", None, 1.5]:
                with self.subTest(field=field, value=value):
                    self.invalid(profile(**{field: value}))
            for value in [minimum, maximum]:
                self.assertEqual(validate_provider(profile(**{field: value}))[field], value)
        for field in ["enabled", "allow_loopback_http"]:
            for value in [0, 1, None, "false"]:
                self.invalid(profile(**{field: value}))

    def test_capabilities_are_bounded_distinct_known_categories(self):
        for value in [
            [], ["unknown"], ["tests", "tests"], "tests", [1],
            ["architecture"], ["tests", "docs", "boilerplate", "mechanical_edit", "extra"],
        ]:
            self.invalid(profile(capabilities=value))
        source = profile(capabilities=["docs"])
        config = validate_provider(source)
        source["capabilities"].append("tests")
        self.assertEqual(config["capabilities"], ["docs"])

    def test_http_is_explicit_and_literal_loopback_only(self):
        for base in [
            "http://127.0.0.1:8080/v1", "http://localhost:8080/v1",
            "http://[::1]:8080/v1",
        ]:
            self.invalid(profile(base, allow_loopback_http=False))
            self.assertEqual(validate_provider(profile(base))["base_url"], base)
        for base in [
            "http://example.invalid/v1", "http://127.0.0.2/v1",
            "http://127.1/v1", "http://2130706433/v1",
            "http://localhost./v1", "http://[::ffff:127.0.0.1]/v1",
        ]:
            self.invalid(profile(base, allow_loopback_http=True))

    def test_urls_reject_credentials_queries_fragments_controls_and_invalid_ports(self):
        for base in [
            "https://user:password@example.invalid/v1",
            "https://user@example.invalid/v1", "https://example.invalid/v1?key=secret",
            "https://example.invalid/v1?", "https://example.invalid/v1#",
            "https://example.invalid/v1#fragment", "https://example.invalid/\nv1",
            "https://example.invalid/%0d%0a/v1", "https://example.invalid/%00/v1",
            " https://example.invalid/v1", "https://example.invalid/v1 ",
            "ftp://example.invalid/v1", "file:///v1", "https:///v1",
            "https://example.invalid:0/v1", "https://example.invalid:65536/v1",
            "https://example.invalid:notaport/v1", "https://[not-ip]/v1",
            "https://example.invalid\\evil/v1",
        ]:
            with self.subTest(base=base):
                self.invalid(profile(base))

    def test_openai_token_parameter_is_explicit(self):
        self.assertEqual(validate_provider(profile(
            max_tokens_field="max_completion_tokens"
        ))["max_tokens_field"], "max_completion_tokens")
        self.invalid(profile(max_tokens_field="auto"))


class ProviderTransportTests(unittest.TestCase):
    def assert_error(self, config, code, **kwargs):
        with self.assertRaises(ProviderError) as error:
            complete(config, kwargs.pop("api_key", SECRET), "system", "user", **kwargs)
        self.assertEqual(error.exception.code, code)
        self.assertNotIn(SECRET, str(error.exception))
        return error.exception

    def test_openai_request_shape_and_actual_usage(self):
        with endpoint() as server:
            result = complete(profile(server["url"]), SECRET, "Review code", "Write tests")
            request = server["requests"][0]
            self.assertEqual(request["path"], "/v1/chat/completions")
            self.assertEqual(request["headers"]["Authorization"], f"Bearer {SECRET}")
            self.assertEqual(request["body"], {
                "model": "exact-user-model", "stream": False,
                "messages": [
                    {"role": "system", "content": "Review code"},
                    {"role": "user", "content": "Write tests"},
                ],
                "max_tokens": 2048,
            })
            self.assertNotIn(SECRET.encode(), request["raw"])
            self.assertEqual(len(server["requests"]), 1)
            self.assertEqual(result["text"], "def add(a, b):\n    return a + b\n")
            self.assertEqual(result["outcome"], "completed")
            self.assertIs(type(result["elapsed_ms"]), int)
            self.assertGreaterEqual(result["elapsed_ms"], 0)
            self.assertEqual(result["usage"], {
                "input_tokens": 31, "output_tokens": 12,
                "cached_input_tokens": 7, "reasoning_tokens": 3,
            })

    def test_openai_completion_limit_field(self):
        with endpoint() as server:
            complete(profile(
                server["url"], max_tokens_field="max_completion_tokens",
                output_limit_tokens=100,
            ), SECRET, "", "user")
            body = server["requests"][0]["body"]
            self.assertEqual(body["max_completion_tokens"], 100)
            self.assertNotIn("max_tokens", body)

    def test_anthropic_request_shape_and_actual_usage(self):
        with endpoint(lambda handler, _: send_response(
            handler, anthropic_response()
        )) as server:
            result = complete(profile(server["url"], protocol="anthropic"),
                              SECRET, "Review code", "Write tests")
            request = server["requests"][0]
            headers = {key.lower(): value for key, value in request["headers"].items()}
            self.assertEqual(request["path"], "/v1/messages")
            self.assertEqual(headers["x-api-key"], SECRET)
            self.assertEqual(headers["anthropic-version"], "2023-06-01")
            self.assertNotIn("authorization", headers)
            self.assertEqual(request["body"], {
                "model": "exact-user-model", "stream": False,
                "system": "Review code",
                "messages": [{"role": "user", "content": "Write tests"}],
                "max_tokens": 2048,
            })
            self.assertEqual(result["text"], "first\nsecond")
            self.assertEqual(result["usage"], {
                "input_tokens": 31, "output_tokens": 12,
                "cached_input_tokens": 7, "reasoning_tokens": 3,
            })

    def test_usage_is_never_estimated_or_coerced(self):
        body = openai_response(usage={
            "prompt_tokens": True, "completion_tokens": "12",
            "prompt_tokens_details": {"cached_tokens": -2},
            "completion_tokens_details": {"reasoning_tokens": 1.5},
        })
        with endpoint(lambda handler, _: send_response(handler, body)) as server:
            result = complete(profile(server["url"]), SECRET, "system", "user")
            self.assertEqual(result["usage"], {
                "input_tokens": None, "output_tokens": None,
                "cached_input_tokens": None, "reasoning_tokens": None,
            })
        for protocol, response in [
            ("openai", openai_response(usage=None)),
            ("anthropic", {**anthropic_response(), "usage": None}),
        ]:
            with endpoint(lambda handler, _: send_response(handler, response)) as server:
                result = complete(profile(server["url"], protocol=protocol),
                                  SECRET, "system", "user")
                self.assertTrue(all(value is None for value in result["usage"].values()))

    def test_pre_send_cancellation_and_local_errors_do_not_send(self):
        cancelled = threading.Event()
        cancelled.set()
        with endpoint() as server:
            error = self.assert_error(profile(server["url"]), "cancelled",
                                      cancelled=cancelled)
            self.assertFalse(error.uncertain)
            for key in ["", "secret\nheader", "secret\rheader", "secret\x00"]:
                error = self.assert_error(profile(server["url"]), "missing_api_key",
                                          api_key=key)
                self.assertFalse(error.uncertain)
            self.assert_error(profile(server["url"], enabled=False), "disabled_provider")
            self.assert_error(profile(server["url"], input_limit_bytes=2), "input_limit")
            self.assertEqual(server["requests"], [])

    def test_utf8_limit_counts_bytes_and_bounds_request(self):
        with endpoint() as server:
            with self.assertRaises(ProviderError) as error:
                complete(profile(server["url"], input_limit_bytes=3), SECRET, "", "你好")
            self.assertEqual(error.exception.code, "input_limit")
            with self.assertRaises(ProviderError):
                complete(profile(server["url"], input_limit_bytes=262144),
                         SECRET, "", "\x00" * 262144)
            self.assertEqual(server["requests"], [])

    def test_redirect_never_forwards_credentials_or_retries(self):
        with endpoint() as destination:
            for status in [301, 302, 303, 307, 308]:
                with endpoint(lambda handler, _, status=status: send_response(
                    handler, b"", status, {"Location": destination["url"] + "/stolen"}
                )) as source:
                    self.assert_error(profile(source["url"]), "redirect")
                    self.assertEqual(len(source["requests"]), 1)
            self.assertEqual(destination["requests"], [])

    def test_http_errors_are_sanitized_and_never_retried(self):
        for status in [400, 401, 403, 408, 413, 429, 500, 503]:
            with endpoint(lambda handler, _, status=status: send_response(
                handler, { "error": { "message": SECRET } }, status
            )) as server:
                error = self.assert_error(profile(server["url"]), f"http_{status}")
                self.assertEqual(error.uncertain, status == 408 or status >= 500)
                self.assertEqual(len(server["requests"]), 1)

    def test_malformed_and_unsupported_response_bodies(self):
        for body in [
            b"not json " + SECRET.encode(), b"\xff", b"[]", b"null",
            b'{"choices":[]}', b'{"choices":null}', b'{"choices": [{ }]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":3}}]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":" "}}]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":"ok"}}],'
            b'"choices":[]}',
        ]:
            with endpoint(lambda handler, _, body=body: send_response(
                handler, body
            )) as server:
                self.assert_error(profile(server["url"]), "invalid_response")

    def test_truncation_refusal_and_tool_calls_preserve_reported_usage(self):
        for finish, code in [
            ("length", "truncated"), ("content_filter", "refused"),
            ("tool_calls", "tool_call"), ("function_call", "tool_call"),
            (None, "invalid_response"),
        ]:
            body = openai_response()
            body["choices"][0]["finish_reason"] = finish
            with endpoint(lambda handler, _: send_response(handler, body)) as server:
                error = self.assert_error(profile(server["url"]), code)
                self.assertEqual(error.usage["input_tokens"], 31)
                self.assertEqual(error.usage["output_tokens"], 12)
        for extra, code in [
            ({"refusal": "declined " + SECRET}, "refused"),
            ({"tool_calls": [{"function": {"name": "write_file"}}]}, "tool_call"),
            ({"function_call": {"name": "write_file"}}, "tool_call"),
        ]:
            body = openai_response()
            body["choices"][0]["message"].update(extra)
            with endpoint(lambda handler, _: send_response(handler, body)) as server:
                self.assert_error(profile(server["url"]), code)

    def test_anthropic_rejects_noncompletion_tool_and_refusal_shapes(self):
        cases = [
            ({"stop_reason": "max_tokens"}, "truncated"),
            ({"stop_reason": "model_context_window_exceeded"}, "truncated"),
            ({"stop_reason": "tool_use"}, "tool_call"),
            ({"stop_reason": "refusal"}, "refused"),
            ({"stop_reason": "pause_turn"}, "invalid_response"),
            ({"stop_details": {"type": "refusal", "explanation": SECRET}}, "refused"),
            ({"content": [{"type": "tool_use", "name": "write_file"}]}, "tool_call"),
            ({"content": [{"type": "server_tool_use", "name": "web_search"}]}, "tool_call"),
            ({"content": [{"type": "refusal", "text": SECRET}]}, "refused"),
            ({"content": [{"type": "text", "text": 5}]}, "invalid_response"),
            ({"content": []}, "invalid_response"),
        ]
        for overrides, code in cases:
            body = anthropic_response()
            body.update(overrides)
            with endpoint(lambda handler, _: send_response(handler, body)) as server:
                error = self.assert_error(
                    profile(server["url"], protocol="anthropic"), code
                )
                self.assertEqual(error.usage["output_tokens"], 12)

    def test_oversized_response_and_content_length_are_bounded(self):
        for body, headers in [
            (b"x" * (1024 * 1024 + 1), None),
            (b"{}", {"Content-Length": str(1024 * 1024 + 1)}),
            (b"{}", {"Content-Length": "invalid"}),
        ]:
            with endpoint(lambda handler, _, body=body, headers=headers: send_response(
                handler, body, headers=headers
            )) as server:
                expected = ("invalid_response" if headers and
                            headers.get("Content-Length") == "invalid"
                            else "response_too_large")
                self.assert_error(profile(server["url"]), expected)

    def test_disconnected_body_is_uncertain(self):
        def responder(handler, _):
            handler.send_response(200)
            handler.send_header("Content-Length", "2000")
            handler.end_headers()
            handler.wfile.write(b'{"partial":')
            handler.wfile.flush()
            handler.connection.shutdown(socket.SHUT_RDWR)
            handler.connection.close()

        with endpoint(responder) as server:
            error = self.assert_error(profile(server["url"]), "network_error")
            self.assertTrue(error.uncertain)
            self.assertEqual(len(server["requests"]), 1)

    def test_total_timeout_is_finite_and_does_not_retry(self):
        def responder(handler, release):
            release.wait(3)
            send_response(handler, openai_response())

        with endpoint(responder) as server:
            started = time.monotonic()
            error = self.assert_error(profile(server["url"], timeout_seconds=1), "timeout")
            self.assertLess(time.monotonic() - started, 1.8)
            self.assertTrue(error.uncertain)
            self.assertEqual(len(server["requests"]), 1)

    def test_slow_drip_cannot_reset_total_deadline(self):
        def responder(handler, release):
            handler.send_response(200)
            handler.send_header("Content-Length", "1000")
            handler.end_headers()
            while not release.wait(0.03):
                handler.wfile.write(b" ")
                handler.wfile.flush()

        with endpoint(responder) as server:
            started = time.monotonic()
            error = self.assert_error(profile(server["url"], timeout_seconds=1), "timeout")
            self.assertTrue(error.uncertain)
            self.assertLess(time.monotonic() - started, 1.8)

    def test_cancellation_after_send_is_prompt_and_uncertain(self):
        def responder(handler, release):
            release.wait(3)
            send_response(handler, openai_response())

        with endpoint(responder) as server:
            cancelled = threading.Event()
            results = []

            def run():
                try:
                    complete(profile(server["url"]), SECRET, "system", "user",
                             cancelled=cancelled)
                except ProviderError as error:
                    results.append(error)

            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(server["received"].wait(1))
            started = time.monotonic()
            cancelled.set()
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertLess(time.monotonic() - started, 0.7)
            self.assertEqual(results[0].code, "cancelled")
            self.assertTrue(results[0].uncertain)
            self.assertEqual(len(server["requests"]), 1)



    def test_invalid_unicode_is_local_and_reported_response_usage_is_preserved(self):
        with endpoint() as server:
            with self.assertRaises(ProviderError) as error:
                complete(profile(server["url"]), SECRET, "", "\ud800")
            self.assertEqual(error.exception.code, "invalid_request")
            with self.assertRaises(ProviderError) as error:
                complete(profile(server["url"], model="\ud800"), SECRET, "", "user")
            self.assertEqual(error.exception.code, "invalid_provider")
            self.assertEqual(server["requests"], [])
        with endpoint(lambda handler, _: send_response(
            handler, openai_response(text="\ud800")
        )) as server:
            error = self.assert_error(profile(server["url"]), "invalid_response")
            self.assertEqual(error.usage["output_tokens"], 12)

    def test_no_content_length_cannot_bypass_response_byte_limit(self):
        def responder(handler, _):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b"x" * (1024 * 1024 + 1))
            handler.wfile.flush()

        with endpoint(responder) as server:
            self.assert_error(profile(server["url"]), "response_too_large")

    def test_chunked_completed_response_is_supported(self):
        def responder(handler, _):
            body = json.dumps(openai_response()).encode()
            handler.send_response(200)
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()
            for part in [body[:15], body[15:]]:
                handler.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
            handler.wfile.write(b"0\r\n\r\n")
            handler.wfile.flush()

        with endpoint(responder) as server:
            result = complete(profile(server["url"]), SECRET, "", "user")
            self.assertEqual(result["outcome"], "completed")
            self.assertEqual(result["usage"]["output_tokens"], 12)

    def test_anthropic_only_returns_text_from_reasoning_models(self):
        body = anthropic_response()
        body["content"].insert(0, {
            "type": "thinking", "thinking": "private reasoning",
            "signature": "synthetic-signature",
        })
        with endpoint(lambda handler, _: send_response(handler, body)) as server:
            result = complete(profile(server["url"], protocol="anthropic"),
                              SECRET, "", "user")
            self.assertEqual(result["text"], "first\nsecond")
            self.assertEqual(result["usage"]["reasoning_tokens"], 3)

    def test_dns_cancellation_returns_before_resolver_and_cannot_send_later(self):
        from unittest.mock import patch

        entered = threading.Event()
        release_dns = threading.Event()
        cancelled = threading.Event()
        real_getaddrinfo = socket.getaddrinfo
        resolver_threads = []
        results = []

        def delayed_resolve(*args, **kwargs):
            resolver_threads.append(threading.current_thread())
            entered.set()
            release_dns.wait(3)
            return real_getaddrinfo(*args, **kwargs)

        def run(config):
            try:
                complete(config, SECRET, "", "user", cancelled=cancelled)
            except ProviderError as error:
                results.append(error)

        with endpoint() as server:
            try:
                with patch("socket.getaddrinfo", delayed_resolve):
                    caller = threading.Thread(target=run, args=(profile(server["url"]),))
                    caller.start()
                    self.assertTrue(entered.wait(1))
                    cancelled.set()
                    caller.join(timeout=1)
                    self.assertFalse(caller.is_alive())
                    self.assertEqual(results[0].code, "cancelled")
                    self.assertFalse(results[0].uncertain)
                    self.assertFalse(release_dns.is_set())
                    release_dns.set()
                    resolver_threads[0].join(timeout=1)
                    self.assertFalse(resolver_threads[0].is_alive())
                    self.assertEqual(server["requests"], [])
            finally:
                release_dns.set()


if __name__ == "__main__":
    unittest.main()
