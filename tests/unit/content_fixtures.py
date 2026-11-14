"""Script fixtures for the craft validators (golden set, AGENT_PROMPTS 'Script craft cases')."""

from __future__ import annotations

import copy
from typing import Any

# 19 words
SENTENCE = "Here is a concrete number from my own spending log and what it taught me about small daily habits"


def _words(n: int) -> str:
    out: list[str] = []
    while len(out) < n:
        out += SENTENCE.split()
    return " ".join(out[:n]) + "."


def long_script(minutes: int = 8) -> dict[str, Any]:
    """A long-form draft that passes every check at 150 wpm (target = minutes × 60 s)."""
    hook = (
        "Last month I wasted nine thousand rupees and I didn't notice until I tracked every single purchase. "
        "Three categories did almost all the damage. One of them is probably draining your money right now."
    )  # 34 words ≈ 13.6 s
    total_words = minutes * 150
    body_words = total_words - 34 - 20 - 15
    per = body_words // 5
    sections = [
        {"heading": h, "text": _words(per), "fact_refs": ["c1"], "beat": b}
        for h, b in [
            ("The first leak", "SETUP"),
            ("Why it hides", "TENSION"),
            ("What the numbers show", "EXPLORATION"),
            ("The turn", "REVEAL"),
            ("The fix", "PAYOFF"),
        ]
    ]
    sections[1]["text"] += " [[OWNER: your biggest surprise in your own log]]"
    sections[3]["text"] += " [[OWNER: the moment you noticed the pattern]]"
    return {
        "promise_delivery": {
            "promise_statement": "Show where 9,000 went",
            "delivered_at_s": 6,
            "text": hook[:60],
        },
        "hook": {"text": hook, "est_s": 13, "technique": ["COLD_OPEN_STORY", "STAKES"]},
        "sections": sections,
        "re_hooks": [
            {"at_pct": 25, "technique": "PROGRESS_MARKER", "text": "That's the first leak."},
            {"at_pct": 50, "technique": "TWIST", "text": "Here's where it got weird."},
            {"at_pct": 75, "technique": "OPEN_LOOP", "text": "Before the fix, look at this number."},
        ],
        "open_loops": [
            {"id": "L1", "opened_in_section": 0, "closed_in_section": 4, "text": "Which leak drains you"}
        ],
        "payoff": _words(20),
        "cta": "If you try the tracker this week, tell me which leak surprised you most.",
        "owner_slots": [
            {"section_index": 1, "prompt": "Biggest surprise"},
            {"section_index": 3, "prompt": "Moment"},
        ],
        "est_duration_s": minutes * 60,
        "word_count": total_words,
    }


def short_script() -> dict[str, Any]:
    """A 45 s Short that passes every check."""
    return {
        "promise_delivery": {
            "promise_statement": "One leak",
            "delivered_at_s": 2,
            "text": "This leak cost me 9,000.",
        },
        "hook": {
            "text": "This tiny habit cost me nine thousand rupees.",
            "est_s": 3,
            "technique": ["STAKES"],
        },
        "sections": [
            {"heading": "Leak", "text": _words(60) + " [[OWNER: your own example]]", "fact_refs": ["c1"]},
            {"heading": "Fix", "text": _words(30), "fact_refs": []},
        ],
        "re_hooks": [],
        "open_loops": [],
        "payoff": "Track it for one week.",
        "cta": "Tell me yours.",
        "owner_slots": [{"section_index": 0, "prompt": "Example"}],
        "est_duration_s": 45,
        "word_count": 112,
    }


def mutate(script: dict[str, Any], **changes: Any) -> dict[str, Any]:
    out = copy.deepcopy(script)
    out.update(changes)
    return out
