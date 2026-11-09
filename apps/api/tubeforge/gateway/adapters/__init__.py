"""Text (LLM) adapters for the AI Provider Gateway. Only the gateway calls them (ADR-0026: httpx)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

ErrorKind = Literal["LIMIT", "TRANSIENT", "AUTH", "INVALID", "PAID_INDICATOR"]
# Text that means "this account is on a paid / billing path" (COST_CONTROL_SPEC §5, A32).
PAID_WORDS = re.compile(
    r"\b(billing|billed|payment|charges?|credit card|paid tier|upgrade your plan)\b", re.I
)


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class TextRequest:
    model: str
    messages: tuple[Message, ...]
    system: str | None = None
    max_output_tokens: int = 1024
    temperature: float = 0.3
    json_mode: bool = False


@dataclass(frozen=True)
class TextResponse:
    text: str
    tokens_in: int
    tokens_out: int
    headers: dict[str, str] = field(default_factory=dict)


class AdapterError(Exception):
    def __init__(
        self, kind: ErrorKind, status: int | None, detail: str, retry_after_s: float | None = None
    ) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.status = status
        self.detail = detail[:300]
        self.retry_after_s = retry_after_s


class TextAdapter(Protocol):
    family: str
    hosts: frozenset[str]
    needs_key: bool

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse: ...


def classify(status: int, body: str, headers: httpx.Headers) -> AdapterError:
    retry = headers.get("retry-after")
    retry_s = float(retry) if retry and retry.replace(".", "", 1).isdigit() else None
    if PAID_WORDS.search(body):
        return AdapterError("PAID_INDICATOR", status, "the provider mentions billing or payment")
    lowered = body.lower()
    if status == 429 or "resource_exhausted" in lowered or "quota" in lowered or "rate limit" in lowered:
        return AdapterError("LIMIT", status, "the provider's limit is reached", retry_s)
    if status in (401, 403) or "api_key_invalid" in lowered or "invalid api key" in lowered:
        return AdapterError("AUTH", status, "the API key was not accepted")
    if status >= 500:
        return AdapterError("TRANSIENT", status, f"provider error {status}")
    return AdapterError("INVALID", status, f"request refused ({status})")


class HttpAdapter:
    family = ""
    hosts: frozenset[str] = frozenset()
    needs_key = True

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 120.0) -> None:
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        self._http.close()

    def _post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        host = httpx.URL(url).host
        if host not in self.hosts:
            raise AdapterError("INVALID", None, f"host {host} is not allowed for {self.family}")
        try:
            resp = self._http.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise AdapterError("TRANSIENT", None, "the provider did not answer in time") from exc
        except httpx.TransportError as exc:
            raise AdapterError("TRANSIENT", None, type(exc).__name__) from exc
        if resp.status_code >= 400:
            raise classify(resp.status_code, resp.text[:2000], resp.headers)
        return resp

    @staticmethod
    def _json(resp: httpx.Response) -> dict[str, Any]:
        try:
            data: dict[str, Any] = resp.json()
        except json.JSONDecodeError as exc:
            raise AdapterError("TRANSIENT", resp.status_code, "unreadable provider response") from exc
        return data
