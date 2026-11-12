"""Adapter request formats and error classification (no network: httpx.MockTransport)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from tubeforge.gateway.adapters import (
    ANSWER_TIMEOUT_S,
    CONNECT_TIMEOUT_S,
    AdapterError,
    Message,
    TextRequest,
)
from tubeforge.gateway.adapters.gemini import GeminiAdapter
from tubeforge.gateway.adapters.groq import GroqAdapter
from tubeforge.gateway.adapters.ollama import OllamaAdapter
from tubeforge.gateway.limits import next_reset, period_key

REQ = TextRequest(
    model="m1", messages=(Message("user", "hello"),), system="be brief", max_output_tokens=50, json_mode=True
)


def capture(reply: httpx.Response) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return reply

    return seen, httpx.MockTransport(handle)


def test_gemini_request_and_response() -> None:
    reply = httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": '{"a":'}, {"text": "1}"}]}}],
            "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
        },
    )
    seen, transport = capture(reply)
    out = GeminiAdapter(transport).text(REQ, "secret-key")
    [req] = seen
    assert req.url == "https://generativelanguage.googleapis.com/v1beta/models/m1:generateContent"
    assert req.headers["x-goog-api-key"] == "secret-key" and "secret-key" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert body["generationConfig"] == {
        "maxOutputTokens": 50,
        "temperature": 0.3,
        "responseMimeType": "application/json",
    }
    assert (out.text, out.tokens_in, out.tokens_out) == ('{"a":1}', 7, 3)


def test_groq_request_and_response() -> None:
    reply = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        },
    )
    seen, transport = capture(reply)
    out = GroqAdapter(transport).text(REQ, "gsk_x")
    body = json.loads(seen[0].content)
    assert seen[0].headers["Authorization"] == "Bearer gsk_x"
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assert body["response_format"] == {"type": "json_object"} and body["max_tokens"] == 50
    assert (out.tokens_in, out.tokens_out) == (4, 2)


def test_ollama_is_local_and_keyless() -> None:
    reply = httpx.Response(200, json={"message": {"content": "{}"}, "prompt_eval_count": 9, "eval_count": 1})
    seen, transport = capture(reply)
    out = OllamaAdapter(transport).text(REQ, None)
    assert seen[0].url.host == "127.0.0.1" and seen[0].url.port == 11434
    body = json.loads(seen[0].content)
    assert body["stream"] is False and body["format"] == "json" and body["options"]["num_predict"] == 50
    assert out.tokens_in == 9


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (429, "Too many requests", "LIMIT"),
        (400, '{"error":{"status":"RESOURCE_EXHAUSTED"}}', "LIMIT"),
        (401, "nope", "AUTH"),
        (400, '{"error":{"message":"API key not valid","details":[{"reason":"API_KEY_INVALID"}]}}', "AUTH"),
        (503, "overloaded", "TRANSIENT"),
        (400, "bad request", "INVALID"),
        (403, "Your project has billing enabled; charges apply", "PAID_INDICATOR"),
    ],
)
def test_error_classification(status: int, body: str, kind: str) -> None:
    _, transport = capture(httpx.Response(status, text=body))
    with pytest.raises(AdapterError) as exc:
        GroqAdapter(transport).text(REQ, "k")
    assert exc.value.kind == kind


def test_network_failure_is_transient_and_hosts_are_pinned() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(AdapterError) as exc:
        OllamaAdapter(httpx.MockTransport(boom)).text(REQ, None)
    assert exc.value.kind == "TRANSIENT"
    adapter = GroqAdapter(httpx.MockTransport(lambda _: httpx.Response(200)))
    with pytest.raises(AdapterError):
        adapter._post("https://evil.example.com/x", {}, {})


def test_period_keys_and_resets_follow_pacific_time() -> None:
    now = datetime(2026, 11, 9, 7, 30, tzinfo=UTC)  # 23:30 PST on the 8th
    assert period_key("DAY", "America/Los_Angeles", now) == "2026-11-08"
    assert period_key("MONTH", "America/Los_Angeles", now) == "2026-11"
    assert next_reset("DAY", "America/Los_Angeles", now) == datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    assert next_reset("MONTH", "America/Los_Angeles", now) == datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def test_long_answers_are_waited_for_but_connecting_is_quick() -> None:
    for adapter in (GeminiAdapter(), GroqAdapter(), OllamaAdapter()):
        timeout = adapter._http.timeout
        assert timeout.read == ANSWER_TIMEOUT_S >= 300
        assert timeout.connect == CONNECT_TIMEOUT_S <= 15
        adapter.close()

    def slow(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(AdapterError, match="did not answer in time") as exc:
        GeminiAdapter(httpx.MockTransport(slow)).text(REQ, "k")
    assert exc.value.kind == "TRANSIENT" and exc.value.status is None
