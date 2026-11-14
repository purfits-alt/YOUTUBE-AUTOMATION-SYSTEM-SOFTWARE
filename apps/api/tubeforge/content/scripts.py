"""Script versions: plain text, fingerprint and a readable diff between two versions."""

from __future__ import annotations

import difflib
import hashlib
import json
from typing import Any

from tubeforge.content import craft


def fingerprint(body: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON body (the approval hash for a locked script)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lines(body: dict[str, Any]) -> list[str]:
    out = [f"[HOOK] {body.get('hook', {}).get('text', '')}"]
    for i, s in enumerate(body.get("sections", [])):
        out.append(f"[{i + 1}. {s.get('heading', '')}]")
        out += [line for line in str(s.get("text", "")).splitlines() if line.strip()]
    out += [f"[PAYOFF] {body.get('payoff', '')}", f"[CTA] {body.get('cta', '')}"]
    return out


def diff(a: dict[str, Any], b: dict[str, Any], label_a: str = "a", label_b: str = "b") -> list[str]:
    return list(
        difflib.unified_diff(_lines(a), _lines(b), fromfile=label_a, tofile=label_b, lineterm="", n=1)
    )


def summary(body: dict[str, Any], wpm: int = craft.DEFAULT_WPM) -> dict[str, Any]:
    word_count, est = craft.measure(body, wpm)
    return {
        "plain_text": craft.plain_text(body),
        "word_count": word_count,
        "est_duration_s": est,
        "content_sha256": fingerprint(body),
    }
