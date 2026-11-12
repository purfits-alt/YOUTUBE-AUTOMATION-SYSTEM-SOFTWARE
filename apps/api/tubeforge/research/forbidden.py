"""Forbidden-phrase scan (AGENT_PROMPTS golden set; PREAMBLE rule 3; CHANNEL_DISCOVERY_SPEC §9).

Discovery, trend, keyword and blueprint outputs must never promise or predict money, views,
subscribers or monetisation. Any hit rejects that piece of output (a candidate is dropped, a
blueprint is not saved) and the reason is shown to the owner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rx, re.IGNORECASE))
    for name, rx in [
        ("guaranteed", r"\bguarantee[ds]?\b"),
        ("will earn", r"\bwill (?:earn|make you|pay you)\b"),
        ("100% monetised", r"\b(?:100\s*%|fully)\s*moneti[sz]"),
        ("monetisation promise", r"\b(?:instant|easy|quick|fast|sure)\s+moneti[sz]"),
        ("get rich", r"\bget rich\b"),
        ("money fast", r"\b(?:make|earn) (?:money|cash) (?:fast|quick(?:ly)?|overnight)\b"),
        ("income claim", r"\bearn \$?\d[\d,.]*\s*k?\s*(?:a|per|/)\s*(?:day|week|month|year)\b"),
        ("certain success", r"\b(?:sure[- ]fire|can'?t fail|risk[- ]free|no[- ]risk)\b"),
        ("viral promise", r"\b(?:will|guaranteed to) go viral\b"),
        ("view promise", r"\b(?:will|guaranteed to) (?:get|reach|hit) \d[\d,.]*\s*k?\s*(?:views|subs\w*)\b"),
    ]
]  # fmt: skip


# The same rules in words, for prompts: tell the model up front what the scan rejects.
AVOID_TEXT = (
    "Never use these words or claims anywhere in the answer: guarantee / guaranteed / guarantees; "
    "'will earn', 'will make you', 'will pay you'; 'get rich'; 'make/earn money fast'; any income per "
    "day/week/month/year; 'fully' or '100%' monetised; easy, instant, quick or sure monetisation; "
    "sure-fire, can't fail, risk-free, no risk; 'will go viral'; promises of a number of views or "
    "subscribers. Say 'may', 'aims to' or 'evidence suggests' instead."
)


def describe(hits: list[Hit]) -> str:
    """Where the answer broke the rules (paths and rule names only; no model text is echoed back)."""
    return "; ".join(f"'{h.phrase}' at {h.path}" for h in hits[:10])


@dataclass(frozen=True)
class Hit:
    path: str
    phrase: str
    excerpt: str


def scan(value: Any, path: str = "$") -> list[Hit]:
    hits: list[Hit] = []
    if isinstance(value, str):
        for name, rx in PATTERNS:
            m = rx.search(value)
            if m:
                start = max(0, m.start() - 30)
                hits.append(Hit(path, name, value[start : m.end() + 30]))
    elif isinstance(value, dict):
        for k, v in value.items():
            hits.extend(scan(v, f"{path}.{k}"))
    elif isinstance(value, list | tuple):
        for i, v in enumerate(value):
            hits.extend(scan(v, f"{path}[{i}]"))
    return hits
