"""Groq (free plan), OpenAI-compatible chat completions."""

from __future__ import annotations

from typing import Any

from tubeforge.gateway.adapters import AdapterError, HttpAdapter, TextRequest, TextResponse

URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqAdapter(HttpAdapter):
    family = "groq"
    hosts = frozenset({"api.groq.com"})

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse:
        if not api_key:
            raise AdapterError("AUTH", None, "no Groq API key")
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = self._post(URL, body, {"Authorization": f"Bearer {api_key}"})
        data = self._json(resp)
        choices = data.get("choices") or []
        if not choices:
            raise AdapterError("INVALID", resp.status_code, "Groq returned no choice")
        usage = data.get("usage") or {}
        return TextResponse(
            text=str((choices[0].get("message") or {}).get("content") or ""),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            headers=dict(resp.headers),
        )
