"""Ollama on this PC (Tier L): nothing leaves the computer, no key, no money."""

from __future__ import annotations

from typing import Any

from tubeforge.gateway.adapters import AdapterError, HttpAdapter, TextRequest, TextResponse

URL = "http://127.0.0.1:11434/api/chat"


class OllamaAdapter(HttpAdapter):
    family = "ollama"
    hosts = frozenset({"127.0.0.1"})  # loopback only
    needs_key = False

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": request.max_output_tokens, "temperature": request.temperature},
        }
        if request.json_mode:
            body["format"] = "json"
        resp = self._post(URL, body, {})
        data = self._json(resp)
        if "message" not in data:
            raise AdapterError("INVALID", resp.status_code, "Ollama returned no message")
        return TextResponse(
            text=str(data["message"].get("content") or ""),
            tokens_in=int(data.get("prompt_eval_count", 0)),
            tokens_out=int(data.get("eval_count", 0)),
            headers=dict(resp.headers),
        )
