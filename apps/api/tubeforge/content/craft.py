"""Script craft validators (AGENT_PROMPTS A11 v1.1, VIDEO_PRODUCTION_SPEC §1a). Code, not AI.

They run on every script draft (agent or owner). Findings with severity ERROR make the agent do
one repair call; for owner edits they are shown in Script Studio. Durations are measured from the
words themselves at the channel's speaking rate (``wpm``); numbers the model reports are not
trusted.
"""

# ruff: noqa: E501  (owner-facing messages read better unwrapped)
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Literal

from tubeforge.research.forbidden import scan

DEFAULT_WPM = 150
HOOK_LONG_S = (10.0, 15.0)
HOOK_SHORT_MAX_S = 3.0
HOOK_SHORT_MAX_WORDS = 10
PROMISE_LONG_S = 15.0
PROMISE_SHORT_S = 3.0
REHOOK_BANDS = ((20, 30), (45, 55), (70, 80))  # % of runtime, long-form
REHOOK_EVERY_S = 120  # videos over 8 minutes: at most this many seconds between re-hooks
LONG_VIDEO_S = 8 * 60
DURATION_TOLERANCE = 0.10
SHORT_MAX_S = 180
OWNER_SLOTS = {"LONG": 2, "SHORT": 1}
OWNER_SLOT = re.compile(r"\[\[OWNER:[^\]]*\]\]")

# AI-sounding filler and pressure tactics (A11 rules 2, 4, 6, 8). Matched case-insensitively.
BANNED_PHRASES = (
    "in today's video",
    "in this video we will",
    "let's dive in",
    "let's dive right in",
    "dive deep",
    "delve",
    "in conclusion",
    "it's important to note",
    "it is important to note",
    "game-changer",
    "game changer",
    "without further ado",
    "welcome back",
    "hey guys",
    "you won't believe",
    "smash that like",
    "subscribe or",
    "giveaway",
    "in the ever-evolving",
    "unlock the secrets",
)

Severity = Literal["ERROR", "WARNING"]
Format = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str


def words(text: str) -> int:
    return len(re.findall(r"[\w’'-]+", text, flags=re.UNICODE))


def seconds(n_words: int, wpm: int = DEFAULT_WPM) -> float:
    return round(n_words * 60 / max(wpm, 1), 1)


def spoken_parts(script: dict[str, Any]) -> list[str]:
    """Hook, sections, payoff and CTA in reading order (the promise sits inside the hook/intro)."""
    parts = [str(script.get("hook", {}).get("text", ""))]
    parts += [str(s.get("text", "")) for s in script.get("sections", [])]
    parts += [str(script.get("payoff", "")), str(script.get("cta", ""))]
    return [p for p in parts if p.strip()]


def plain_text(script: dict[str, Any]) -> str:
    return "\n\n".join(spoken_parts(script))


def measure(script: dict[str, Any], wpm: int = DEFAULT_WPM) -> tuple[int, int]:
    """(word_count, est_duration_s) from the text itself."""
    n = sum(words(p) for p in spoken_parts(script))
    return n, round(seconds(n, wpm))


def check_script(
    script: dict[str, Any],
    *,
    fmt: Format,
    target_duration_s: int,
    wpm: int = DEFAULT_WPM,
    recent_phrases: tuple[str, ...] = (),
    claim_ids: set[str] | None = None,
) -> list[Finding]:
    out: list[Finding] = []
    sections = list(script.get("sections", []))
    hook = str(script.get("hook", {}).get("text", ""))
    hook_words = words(hook)
    hook_s = seconds(hook_words, wpm)
    _, total_s = measure(script, wpm)

    # 1. Hook length
    if fmt == "LONG":
        low, high = HOOK_LONG_S
        if not low <= hook_s <= high:
            out.append(Finding(
                "HOOK_LENGTH", "ERROR",
                f"The hook is {hook_words} words (≈ {hook_s:g} s); "
                f"it should take {low:g}–{high:g} s at {wpm} wpm.",
            ))  # fmt: skip
    elif hook_words > HOOK_SHORT_MAX_WORDS or hook_s > HOOK_SHORT_MAX_S + 1:
        out.append(Finding(
            "HOOK_LENGTH", "ERROR",
            f"A Short's hook must be the first 1–3 s (≤ {HOOK_SHORT_MAX_WORDS} words); "
            f"it is {hook_words} words.",
        ))  # fmt: skip
    if re.match(r"\s*(hi|hello|hey|welcome)\b", hook, flags=re.IGNORECASE):
        out.append(
            Finding("HOOK_GREETING", "ERROR", "No greeting before the hook; start with the hook itself.")
        )

    # 2. Promise in the intro
    promise = script.get("promise_delivery") or {}
    limit = PROMISE_LONG_S if fmt == "LONG" else PROMISE_SHORT_S
    if not str(promise.get("text", "")).strip():
        out.append(Finding("PROMISE_MISSING", "ERROR", "The intro does not address the packaging promise."))
    else:
        at = float(promise.get("delivered_at_s", limit + 1))
        if at > limit:
            out.append(Finding(
                "PROMISE_LATE", "ERROR", f"The promise is addressed at {at:g} s; it must come within {limit:g} s.",
            ))  # fmt: skip

    # 3. Re-hooks (long-form)
    if fmt == "LONG":
        positions = sorted(float(r.get("at_pct", -1)) for r in script.get("re_hooks", []))
        missing = [f"{a}–{b} %" for a, b in REHOOK_BANDS if not any(a <= p <= b for p in positions)]
        if missing:
            out.append(
                Finding(
                    "REHOOK_MISSING", "ERROR", "Add re-hooks around " + ", ".join(missing) + " of the video."
                )
            )
        if total_s > LONG_VIDEO_S and positions:
            marks = [0.0, *[p / 100 * total_s for p in positions], float(total_s)]
            widest = max(b - a for a, b in pairwise(marks))
            if widest > REHOOK_EVERY_S * (1 + DURATION_TOLERANCE):
                out.append(Finding(
                    "REHOOK_SPARSE", "WARNING",
                    f"There are {widest:.0f} s without a re-hook; videos over 8 minutes need one every 60–120 s.",
                ))  # fmt: skip

    # 4. Open loops
    for loop in script.get("open_loops", []):
        opened, closed = int(loop.get("opened_in_section", -1)), loop.get("closed_in_section")
        if closed is None or int(closed) <= opened or int(closed) >= len(sections):
            out.append(Finding(
                "OPEN_LOOP_UNCLOSED", "ERROR",
                f"Open loop “{str(loop.get('text', loop.get('id', '?')))[:60]}” is not closed in a later section.",
            ))  # fmt: skip

    # 5. Banned phrases (filler, pressure, repeats of recent scripts, forbidden promises)
    text = plain_text(script)
    low_text = text.lower()
    for phrase in (*BANNED_PHRASES, *(p.lower() for p in recent_phrases if p.strip())):
        if phrase in low_text:
            out.append(Finding("BANNED_PHRASE", "ERROR", f"Avoid “{phrase}”."))
    for hit in scan(text):
        out.append(
            Finding("FORBIDDEN_PROMISE", "ERROR", f"Remove the promise “{hit.phrase}”: {hit.excerpt.strip()}")
        )

    # 6. Duration
    if target_duration_s > 0 and abs(total_s - target_duration_s) > target_duration_s * DURATION_TOLERANCE:
        out.append(Finding(
            "DURATION", "ERROR",
            f"The script reads in about {total_s} s; the target is {target_duration_s} s ± 10 %.",
        ))  # fmt: skip
    if fmt == "SHORT" and total_s > SHORT_MAX_S:
        out.append(
            Finding(
                "SHORT_TOO_LONG", "ERROR", f"A Short must stay under {SHORT_MAX_S} s; this is {total_s} s."
            )
        )

    # 7. Owner slots
    slots = max(len(script.get("owner_slots", [])), len(OWNER_SLOT.findall(text)))
    need = OWNER_SLOTS[fmt]
    if slots < need:
        out.append(Finding(
            "OWNER_SLOTS", "ERROR", f"Leave at least {need} [[OWNER: …]] slot(s) for your own stories ({slots} now).",
        ))  # fmt: skip

    # 8. Facts point at known claims
    if claim_ids is not None:
        unknown = sorted({r for s in sections for r in s.get("fact_refs", []) if r not in claim_ids})
        if unknown:
            out.append(Finding("FACT_REF_UNKNOWN", "ERROR", "Unknown claim ids: " + ", ".join(unknown[:10])))
    return out


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "ERROR"]
