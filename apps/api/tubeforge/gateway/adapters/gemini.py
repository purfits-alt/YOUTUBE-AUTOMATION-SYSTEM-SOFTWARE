"""Gemini API (free tier only — the key must come from a Cloud project with NO billing linked)."""

from __future__ import annotations

from typing import Any

from tubeforge.gateway.adapters import AdapterError, HttpAdapter, TextRequest, TextResponse

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiAdapter(HttpAdapter):
    family = "gemini"
    hosts = frozenset({"generativelanguage.googleapis.com"})

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse:
        if not api_key:
            raise AdapterError("AUTH", None, "no Gemini API key")
        body: dict[str, Any] = {
            "contents": [
                {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                for m in request.messages
            ],
            "generationConfig": {
                "maxOutputTokens": request.max_output_tokens,
                "temperature": request.temperature,
                **({"responseMimeType": "application/json"} if request.json_mode else {}),
            },
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        # The key goes in a header (Google's x-goog-api-key), never in the URL, so it cannot end up in logs.
        resp = self._post(f"{BASE}/{request.model}:generateContent", body, {"x-goog-api-key": api_key})
        data = self._json(resp)
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no answer")
            raise AdapterError("INVALID", resp.status_code, f"Gemini returned no candidate ({reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        usage = data.get("usageMetadata") or {}
        return TextResponse(
            text="".join(str(p.get("text", "")) for p in parts),
            tokens_in=int(usage.get("promptTokenCount", 0)),
            tokens_out=int(usage.get("candidatesTokenCount", 0)),
            headers=dict(resp.headers),
        )
