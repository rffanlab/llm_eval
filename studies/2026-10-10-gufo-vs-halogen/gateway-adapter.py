#!/usr/bin/env python3
"""Authenticated multi-port proxy for one OpenAI-compatible model backend.

The backend stays on loopback.  Public model aliases are rewritten to the
backend's configured model id so existing Qwen clients can survive a model
upgrade without sending credentials to the inference container.
"""

from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
import signal
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit


MAX_REQUEST_BYTES = 64 * 1024 * 1024
COPY_RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-encoding",
    "content-language",
    "content-type",
    "retry-after",
    "x-request-id",
}


def parse_backend(url: str) -> tuple[str, int]:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError(f"unsupported backend URL: {url!r}")
    return parsed.hostname, parsed.port or 80


def parse_listener(value: str) -> tuple[str, int]:
    try:
        host, raw_port = value.rsplit(":", 1)
        port = int(raw_port)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"listener must be HOST:PORT, got {value!r}") from exc
    if not host or not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"listener must be HOST:PORT, got {value!r}")
    return host, port


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3.8-Flash-Next")
MODEL_ALIASES = tuple(
    dict.fromkeys(
        [
            MODEL_ID,
            *(
                alias.strip()
                for alias in os.environ.get("MODEL_ALIASES", "").split(",")
                if alias.strip()
            ),
        ]
    )
)
ALLOWED_REASONING_EFFORTS = frozenset(
    value.strip()
    for value in os.environ.get("MODEL_ALLOWED_REASONING_EFFORTS", "").split(",")
    if value.strip()
)
BACKEND = parse_backend(os.environ.get("MODEL_BACKEND", "http://127.0.0.1:8731"))
API_KEY = os.environ.get("LLAMA_API_KEY", "")
BACKEND_AUTH_FORWARD = os.environ.get("MODEL_BACKEND_AUTH_FORWARD", "0") == "1"
BACKEND_HEALTH_PATH = os.environ.get("MODEL_BACKEND_HEALTH_PATH", "/health")
MODEL_CONTEXT_LENGTH = positive_int_env("MODEL_CONTEXT_LENGTH", 262144)
MODEL_MAX_OUTPUT_TOKENS_CAP = positive_int_env("MODEL_MAX_OUTPUT_TOKENS_CAP", 65536)
MODEL_DEFAULT_OUTPUT_TOKENS = positive_int_env("MODEL_DEFAULT_OUTPUT_TOKENS", 16384)
MODEL_RECOMMENDED_OUTPUT_TOKENS = positive_int_env(
    "MODEL_RECOMMENDED_OUTPUT_TOKENS",
    positive_int_env("MODEL_MAX_OUTPUT_TOKENS", 32000),
)
MODEL_CAPABILITY_CACHE_TTL = positive_int_env("MODEL_CAPABILITY_CACHE_TTL", 60)

_capability_lock = threading.Lock()
_capability_last_probe = 0.0
_capability_cache: dict[str, Any] = {
    "context_length": MODEL_CONTEXT_LENGTH,
    "max_output_tokens": MODEL_MAX_OUTPUT_TOKENS_CAP,
    "default_max_output_tokens": MODEL_DEFAULT_OUTPUT_TOKENS,
    "recommended_max_output_tokens": MODEL_RECOMMENDED_OUTPUT_TOKENS,
    "metadata_source": "environment_fallback",
}


def positive_int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback


def fetch_backend_health() -> dict[str, Any] | None:
    connection = http.client.HTTPConnection(*BACKEND, timeout=3)
    try:
        headers = {"Connection": "close"}
        if BACKEND_AUTH_FORWARD:
            headers["Authorization"] = "Bearer " + API_KEY
        connection.request("GET", BACKEND_HEALTH_PATH, headers=headers)
        response = connection.getresponse()
        body = response.read()
        if response.status != 200:
            return None
        payload = json.loads(body)
        return payload if isinstance(payload, dict) and payload.get("status") in {"ok", "ready"} else None
    except (
        ConnectionError,
        OSError,
        socket.timeout,
        http.client.HTTPException,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return None
    finally:
        connection.close()


def cache_backend_capabilities(payload: dict[str, Any]) -> dict[str, Any]:
    global _capability_cache, _capability_last_probe
    with _capability_lock:
        context_length = positive_int(payload.get("context"), MODEL_CONTEXT_LENGTH)
        max_output_tokens = positive_int(
            payload.get("max_tokens_cap"), MODEL_MAX_OUTPUT_TOKENS_CAP
        )
        default_max_output_tokens = positive_int(
            payload.get("max_tokens_default"), MODEL_DEFAULT_OUTPUT_TOKENS
        )
        _capability_cache = {
            "context_length": context_length,
            "max_output_tokens": max_output_tokens,
            "default_max_output_tokens": min(default_max_output_tokens, max_output_tokens),
            "recommended_max_output_tokens": min(
                MODEL_RECOMMENDED_OUTPUT_TOKENS, max_output_tokens
            ),
            "metadata_source": "backend_health",
        }
        _capability_last_probe = time.monotonic()
        return dict(_capability_cache)


def cached_capabilities(*, probe: bool = True) -> dict[str, Any]:
    global _capability_last_probe
    now = time.monotonic()
    with _capability_lock:
        if not probe or now - _capability_last_probe < MODEL_CAPABILITY_CACHE_TTL:
            return dict(_capability_cache)
        # Throttle failed probes too, so a loading backend cannot stall every
        # model-discovery request.
        _capability_last_probe = now
    payload = fetch_backend_health()
    if payload is not None:
        return cache_backend_capabilities(payload)
    with _capability_lock:
        return dict(_capability_cache)


def model_metadata(model: str, capabilities: dict[str, Any]) -> dict[str, Any]:
    """Return capacity metadata in the spellings used by common clients.

    DeepSeek Harness discovers OpenAI-compatible model capacity from the
    snake_case fields.  The additional aliases keep the endpoint useful for
    clients following vLLM, llama.cpp, or camelCase conventions.
    """
    context_length = capabilities["context_length"]
    max_output_tokens = capabilities["max_output_tokens"]
    return {
        "id": model,
        "object": "model",
        "created": 0,
        "owned_by": "local",
        "context_window": context_length,
        "context_length": context_length,
        "max_context_length": context_length,
        "max_model_len": context_length,
        "contextWindow": context_length,
        "max_output_tokens": max_output_tokens,
        "max_tokens": max_output_tokens,
        "maxTokens": max_output_tokens,
        "default_max_output_tokens": capabilities["default_max_output_tokens"],
        "recommended_max_output_tokens": capabilities["recommended_max_output_tokens"],
        "metadata_source": capabilities["metadata_source"],
        "is_active": True,
    }


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ai-brain-openai-proxy/2.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # BaseHTTPRequestHandler does not log request bodies or headers.  Keep
        # the access log useful while ensuring the bearer token is never shown.
        super().log_message(fmt, *args)

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _openai_error(self, status: int, message: str, code: str) -> None:
        self._json_response(
            status,
            {"error": {"message": message, "type": "invalid_request_error", "code": code}},
        )

    def _authorized(self) -> bool:
        if not API_KEY:
            self._openai_error(503, "API key is not configured", "proxy_misconfigured")
            return False
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {API_KEY}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            self._openai_error(401, "invalid API key", "invalid_api_key")
            return False
        return True

    def _request_headers(self, body_length: int | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name, value in self.headers.items():
            if name.lower() in {
                "authorization",
                "connection",
                "content-length",
                "host",
                "transfer-encoding",
            }:
                continue
            headers[name] = value
        if body_length is not None:
            headers["Content-Length"] = str(body_length)
        headers["Connection"] = "close"
        if BACKEND_AUTH_FORWARD:
            headers["Authorization"] = "Bearer " + API_KEY
        return headers

    def _relay(self, body: bytes | None = None) -> None:
        connection = http.client.HTTPConnection(*BACKEND, timeout=3600)
        try:
            connection.request(
                self.command,
                self.path,
                body=body,
                headers=self._request_headers(None if body is None else len(body)),
            )
            upstream = connection.getresponse()
            content_type = upstream.getheader("Content-Type", "")
            is_stream = "text/event-stream" in content_type.lower()
            if not is_stream:
                response_body = upstream.read()
                self.send_response(upstream.status, upstream.reason)
                for name, value in upstream.getheaders():
                    if name.lower() in COPY_RESPONSE_HEADERS or name.lower().startswith("x-"):
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(response_body)
                self.close_connection = True
                return

            self.send_response(upstream.status, upstream.reason)
            for name, value in upstream.getheaders():
                if name.lower() in COPY_RESPONSE_HEADERS or name.lower().startswith("x-"):
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while chunk := upstream.read(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
            self.close_connection = True
        except (ConnectionError, OSError, socket.timeout, http.client.HTTPException) as exc:
            if not self.wfile.closed:
                self._json_response(
                    503,
                    {"error": {"message": f"model backend unavailable: {exc}", "type": "server_error", "code": "backend_unavailable"}},
                )
        finally:
            connection.close()

    def _read_and_rewrite_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._openai_error(400, "invalid Content-Length", "invalid_content_length")
            return None
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._openai_error(413, "request body is empty or too large", "invalid_request_size")
            return None
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._openai_error(400, "request body must be valid JSON", "invalid_json")
            return None
        if not isinstance(payload, dict):
            self._openai_error(400, "request body must be a JSON object", "invalid_json")
            return None
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            self._openai_error(400, "the model field is required", "model_required")
            return None
        if model not in MODEL_ALIASES:
            self._openai_error(404, f"unknown model: {model}", "model_not_found")
            return None
        if ALLOWED_REASONING_EFFORTS:
            effort = payload.pop("reasoning_effort", None)
            kwargs = payload.get("chat_template_kwargs")
            if kwargs is not None and not isinstance(kwargs, dict):
                self._openai_error(400, "chat_template_kwargs must be an object", "invalid_chat_template_kwargs")
                return None
            if effort is not None:
                if not isinstance(effort, str) or effort not in ALLOWED_REASONING_EFFORTS:
                    self._openai_error(400, "reasoning_effort must be low, medium, or xhigh", "invalid_reasoning_effort")
                    return None
                kwargs = dict(kwargs or {})
                kwargs["reasoning_effort"] = effort
                payload["chat_template_kwargs"] = kwargs
            elif kwargs is not None and "reasoning_effort" in kwargs:
                effort = kwargs["reasoning_effort"]
                if not isinstance(effort, str) or effort not in ALLOWED_REASONING_EFFORTS:
                    self._openai_error(400, "reasoning_effort must be low, medium, or xhigh", "invalid_reasoning_effort")
                    return None
        payload["model"] = MODEL_ID
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            backend_health = fetch_backend_health()
            ready = backend_health is not None
            capabilities = (
                cache_backend_capabilities(backend_health)
                if backend_health is not None
                else cached_capabilities(probe=False)
            )
            self._json_response(
                200 if ready else 503,
                {
                    "status": "ok" if ready else "loading",
                    "model": MODEL_ID,
                    "ready": ready,
                    "context_length": capabilities["context_length"],
                    "context_window": capabilities["context_length"],
                    "max_output_tokens": capabilities["max_output_tokens"],
                    "default_max_output_tokens": capabilities[
                        "default_max_output_tokens"
                    ],
                    "recommended_max_output_tokens": capabilities[
                        "recommended_max_output_tokens"
                    ],
                    "metadata_source": capabilities["metadata_source"],
                },
            )
            return
        if path == "/v1/models":
            capabilities = cached_capabilities()
            data = [model_metadata(model, capabilities) for model in MODEL_ALIASES]
            self._json_response(200, {"object": "list", "data": data})
            return
        if path.startswith("/v1/models/"):
            model = unquote(path[len("/v1/models/") :])
            if model not in MODEL_ALIASES:
                self._openai_error(404, f"unknown model: {model}", "model_not_found")
                return
            self._json_response(
                200,
                model_metadata(model, cached_capabilities()),
            )
            return
        self._json_response(200, {"service": "ai-brain-openai-proxy", "models": list(MODEL_ALIASES)})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        body = self._read_and_rewrite_body()
        if body is not None:
            self._relay(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", type=parse_listener, action="append")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, action="append")
    args = parser.parse_args()

    if args.listen:
        if args.host is not None or args.port:
            parser.error("--listen cannot be combined with --host or --port")
        listeners = args.listen
    else:
        if not args.port:
            parser.error("at least one --listen or --port is required")
        listeners = [(args.host or "0.0.0.0", port) for port in args.port]

    servers = [ThreadingHTTPServer(listener, ProxyHandler) for listener in listeners]
    for server in servers:
        server.daemon_threads = True
    workers = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for worker in workers:
        worker.start()

    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    stopping.wait()
    for server in servers:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
