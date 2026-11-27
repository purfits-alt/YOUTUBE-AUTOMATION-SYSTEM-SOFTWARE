"""Script versions: plain text, fingerprint and a readable diff between two versions."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from typing import Any

from tubeforge.content import craft


def content(body: dict[str, Any]) -> dict[str, Any]:
    """The script itself, without TubeForge's bookkeeping keys (those start with ``_``)."""
    return {k: v for k, v in body.items() if not k.startswith("_")}


def fingerprint(body: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON script (the approval hash for a locked script). Bookkeeping keys
    such as ``_fact_check`` are not part of it."""
    canonical = json.dumps(content(body), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
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


def open_owner_slots(body: dict[str, Any]) -> list[dict[str, str]]:
    """The ``[[OWNER: …]]`` places still waiting for the owner's own words, in reading order:
    ``{"field": "sections.2", "marker": "[[OWNER: …]]", "prompt": "…"}``. A script with any of these
    cannot be approved (owner report 2026-11-27: the prompts reached the storyboard unfilled)."""
    fields: list[tuple[str, str]] = [
        ("hook", str((body.get("hook") or {}).get("text", ""))),
        ("promise_delivery", str((body.get("promise_delivery") or {}).get("text", ""))),
        *((f"sections.{i}", str(s.get("text", ""))) for i, s in enumerate(body.get("sections", []))),
        ("payoff", str(body.get("payoff", ""))),
        ("cta", str(body.get("cta", ""))),
    ]
    return [
        {"field": name, "marker": m.group(0), "prompt": m.group(0)[len("[[OWNER:") : -2].strip()}
        for name, text in fields
        for m in craft.OWNER_SLOT.finditer(text)
    ]


def _tidy(text: str) -> str:
    """Spacing left after taking a marker out of a sentence."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def lift_owner_slots(body: dict[str, Any]) -> dict[str, Any]:
    """Take every empty ``[[OWNER: …]]`` out of the spoken text and keep its prompt as an optional
    suggestion in ``owner_slots`` (owner decision 2026-11-27: adding your own value is optional, and a
    prompt must never be read aloud). The script stays complete without the owner's words."""
    out: dict[str, Any] = json.loads(json.dumps(body))
    suggestions: list[dict[str, Any]] = list(out.get("owner_slots") or [])
    known = {str(s.get("prompt", "")).strip().lower() for s in suggestions}
    last = max(0, len(out.get("sections", [])) - 1)

    def lift(text: str, section_index: int) -> str:
        for m in craft.OWNER_SLOT.finditer(text):
            prompt = m.group(0)[len("[[OWNER:") : -2].strip()
            if prompt and prompt.lower() not in known and len(suggestions) < 10:
                suggestions.append({"section_index": section_index, "prompt": prompt[:200]})
                known.add(prompt.lower())
        return _tidy(craft.OWNER_SLOT.sub("", text)) if craft.OWNER_SLOT.search(text) else text

    for key in ("hook", "promise_delivery"):
        if isinstance(out.get(key), dict) and "text" in out[key]:
            out[key]["text"] = lift(str(out[key]["text"]), 0)
    for i, section in enumerate(out.get("sections", [])):
        section["text"] = lift(str(section.get("text", "")), i)
    for key in ("payoff", "cta"):
        if key in out:
            out[key] = lift(str(out[key]), last)
    out["owner_slots"] = suggestions
    return out


def summary(body: dict[str, Any], wpm: int = craft.DEFAULT_WPM) -> dict[str, Any]:
    word_count, est = craft.measure(body, wpm)
    return {
        "plain_text": craft.plain_text(body),
        "word_count": word_count,
        "est_duration_s": est,
        "content_sha256": fingerprint(body),
    }
