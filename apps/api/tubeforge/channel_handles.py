"""YouTube @handle suggestions from the approved channel name (owner request, 2026-11-15).

YouTube has no API to set or reserve a handle, and checking availability would mean scraping
(ADR-0015), so TubeForge only *suggests*: the owner picks one in YouTube Studio, which says
whether it is free. Rules followed (YouTube Help "Handle" requirements): 3–30 characters;
letters, digits, underscore, hyphen and period; no leading or trailing symbol; not URL-like.
"""

from __future__ import annotations

import re
import unicodedata

MIN_LEN, MAX_LEN = 3, 30
_VALID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{1,28})[A-Za-z0-9]$")
_URL_LIKE = re.compile(r"\.(com|net|org|io|co|ai|app|tv)$", re.IGNORECASE)


def is_valid_handle(handle: str) -> bool:
    h = handle.removeprefix("@")
    return bool(_VALID.match(h)) and not _URL_LIKE.search(h) and ".." not in h


def _words(text: str) -> list[str]:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return [w for w in re.split(r"[^A-Za-z0-9]+", ascii_text) if w]


def _camel(words: list[str]) -> str:
    return "".join(w if w.isupper() and len(w) <= 4 else w[:1].upper() + w[1:] for w in words)


def suggest_handles(channel_name: str, niche_name: str = "", limit: int = 6) -> list[str]:
    """Up to ``limit`` valid, distinct handles (with '@'), most natural first."""
    words = _words(channel_name) or _words(niche_name)
    while len(words) > 1 and len(_camel(words)) > MAX_LEN - 3:  # keep whole words, leave room for "The"
        words = words[:-1]
    if not words:
        return []
    base = _camel(words)
    parts = [_camel([w]) for w in words]
    candidates = [
        base,
        "_".join(parts),
        ".".join(parts),
        f"The{base}",
        f"{base}HQ",
        f"{base}Channel",
        f"{base}Official",
    ]
    out: list[str] = []
    for c in candidates:
        if len(c) > MAX_LEN or len(c) < MIN_LEN or not is_valid_handle(c):
            continue
        if f"@{c}".lower() not in {o.lower() for o in out}:
            out.append(f"@{c}")
        if len(out) == limit:
            break
    return out
