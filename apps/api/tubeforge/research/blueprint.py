"""Channel blueprint: composition and checks in code (CHANNEL_DISCOVERY_SPEC §4, §9).

A06 (strategy) and A07 (branding) write the parts; this module joins them and enforces the rules
models are not trusted with:

- the JSON schema ``packages/shared/schemas/channel_blueprint.json``;
- fonts only from the licensed-font registry (all OFL-1.1 or Apache-2.0);
- a palette contrast pair of at least 4.5:1 (WCAG AA) for thumbnail text, picked in code;
- 50 ideas, no two with similarity ≥ 0.85 (character-trigram cosine of the titles);
- calendar caps: ≤ 1 long-form per day, ≤ 7 per 7 days, ≤ 2 Shorts per day; calendar entries must
  point at an idea of the same format;
- idea pillars must be blueprint pillars;
- no forbidden phrases.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import cache
from itertools import combinations
from typing import Any

import jsonschema_rs

from tubeforge.config import REPO_ROOT
from tubeforge.research.forbidden import scan
from tubeforge.research.scoring import FOOTER

SCHEMA_PATH = REPO_ROOT / "packages" / "shared" / "schemas" / "channel_blueprint.json"
AVAILABILITY_NOTE = "Check availability on YouTube, social platforms and trademarks manually"
LICENSED_FONTS: dict[str, str] = {
    "Inter": "OFL-1.1",
    "Noto Sans": "OFL-1.1",
    "Noto Serif": "OFL-1.1",
    "Noto Nastaliq Urdu": "OFL-1.1",
    "Roboto": "Apache-2.0",
    "Open Sans": "OFL-1.1",
    "Lato": "OFL-1.1",
    "Montserrat": "OFL-1.1",
    "Poppins": "OFL-1.1",
    "Oswald": "OFL-1.1",
    "Bebas Neue": "OFL-1.1",
    "Merriweather": "OFL-1.1",
    "Source Sans 3": "OFL-1.1",
}
SIMILARITY_LIMIT = 0.85
MIN_CONTRAST = 4.5
CAPS = {"long_per_day": 1, "long_per_week": 7, "shorts_per_day": 2}
IDEAS = 50
NO_PAIR = {"text": "#000000", "background": "#000000", "ratio": 1.0}


@cache
def schema_validator() -> Any:
    return jsonschema_rs.validator_for(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


# ------------------------------------------------------------------------------------- colours
def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def best_contrast_pair(palette: list[dict[str, str]]) -> dict[str, Any] | None:
    best: tuple[float, str, str] | None = None
    for x, y in combinations([p["hex"].upper() for p in palette], 2):
        r = contrast_ratio(x, y)
        if best is None or r > best[0]:
            light, dark = (x, y) if _luminance(x) >= _luminance(y) else (y, x)
            best = (r, light, dark)
    if best is None or best[0] < MIN_CONTRAST:
        return None
    return {"text": best[1], "background": best[2], "ratio": best[0]}


# ---------------------------------------------------------------------------------- similarity
def _trigrams(text: str) -> Counter[str]:
    norm = " " + re.sub(r"[^\w]+", " ", text.lower()).strip() + " "
    return Counter(norm[i : i + 3] for i in range(len(norm) - 2))


def similarity(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    dot = sum(ta[k] * tb[k] for k in ta.keys() & tb.keys())
    na, nb = math.sqrt(sum(v * v for v in ta.values())), math.sqrt(sum(v * v for v in tb.values()))
    return 0.0 if not na or not nb else round(dot / (na * nb), 4)


def near_duplicates(titles: list[str]) -> list[tuple[int, int, float]]:
    pairs = []
    for i, j in combinations(range(len(titles)), 2):
        s = similarity(titles[i], titles[j])
        if s >= SIMILARITY_LIMIT:
            pairs.append((i, j, s))
    return pairs


# ------------------------------------------------------------------------------------ calendar
def calendar_problems(calendar: list[dict[str, Any]], ideas: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    long_by_day: Counter[int] = Counter()
    short_by_day: Counter[int] = Counter()
    for entry in calendar:
        day, ref, fmt = int(entry["day"]), int(entry["idea_ref"]), entry["format"]
        if ref >= len(ideas) or ideas[ref]["format"] != fmt:
            problems.append(f"Calendar day {day} points at idea {ref}, which is not a {fmt} idea.")
        (long_by_day if fmt == "LONG" else short_by_day)[day] += 1
    for day in range(1, 31):
        if long_by_day[day] > CAPS["long_per_day"]:
            problems.append(
                f"Day {day} has {long_by_day[day]} long-form videos (limit {CAPS['long_per_day']})."
            )
        if short_by_day[day] > CAPS["shorts_per_day"]:
            problems.append(f"Day {day} has {short_by_day[day]} Shorts (limit {CAPS['shorts_per_day']}).")
        week = sum(long_by_day[d] for d in range(day, min(day + 7, 31)))
        if week > CAPS["long_per_week"]:
            problems.append(
                f"Days {day}–{day + 6} have {week} long-form videos (limit {CAPS['long_per_week']})."
            )
    return problems


# ------------------------------------------------------------------------------------- compose
def compose(niche: dict[str, Any], strategy: dict[str, Any], branding: dict[str, Any]) -> dict[str, Any]:
    """Join A06 + A07 output into one blueprint; fonts get their licence; contrast is picked here."""
    fonts = [
        {"family": f["family"], "use": f["use"], "licence": LICENSED_FONTS.get(f["family"], "UNLICENSED")}
        for f in branding.get("fonts", [])
    ]
    palette = [{"hex": p["hex"].upper(), "role": p["role"]} for p in branding.get("palette", [])]
    return {
        "schema_version": 1,
        "niche": niche,
        "name_ideas": [
            {"name": n["name"], "reason": n["reason"], "availability_note": AVAILABILITY_NOTE}
            for n in branding.get("name_ideas", [])
        ],
        "description": branding.get("description", ""),
        "brand": {
            "tone": branding.get("tone", []),
            "palette": palette,
            "contrast_pair": best_contrast_pair(palette)
            or {"text": "#000000", "background": "#000000", "ratio": 1.0},
            "fonts": fonts,
            "logo_brief": branding.get("logo_brief", ""),
            "banner_brief": branding.get("banner_brief", ""),
        },
        "positioning": strategy.get("positioning", ""),
        "target_audience": strategy.get("target_audience", {"description": "", "needs": []}),
        "pillars": strategy.get("pillars", []),
        "formats": strategy.get("formats", []),
        "calendar_30d": strategy.get("calendar_30d", []),
        "ideas": strategy.get("ideas", []),
        "growth_strategy": strategy.get("growth_strategy", []),
        "risks": strategy.get("risks", []),
        "footer": FOOTER,
    }


def problems(blueprint: dict[str, Any]) -> list[str]:
    """Every rule the blueprint breaks, in plain language. Empty list = valid."""
    out = [
        f"Schema /{'/'.join(str(p) for p in e.instance_path)}: {e.message}"[:300]
        for e in schema_validator().iter_errors(blueprint)
    ]
    if out:
        return out[:20]
    brand = blueprint["brand"]
    for f in brand["fonts"]:
        if f["family"] not in LICENSED_FONTS:
            out.append(f"Font '{f['family']}' is not in the licensed-font list.")
    if brand["contrast_pair"]["ratio"] < MIN_CONTRAST:
        out.append("No two palette colours reach a 4.5:1 contrast for thumbnail text.")
    formats = {f["format"] for f in blueprint["formats"]}
    if formats != {"LONG", "SHORT"}:
        out.append("The formats must include both long-form and Shorts.")
    pillars = {p["name"] for p in blueprint["pillars"]}
    ideas = blueprint["ideas"]
    for i, idea in enumerate(ideas):
        if idea["pillar"] not in pillars:
            out.append(f"Idea {i} uses pillar '{idea['pillar']}', which is not a blueprint pillar.")
    for i, j, s in near_duplicates([x["title"] for x in ideas]):
        out.append(f"Ideas {i} and {j} are near-duplicates (similarity {s:.2f}).")
    out.extend(calendar_problems(blueprint["calendar_30d"], ideas))
    out.extend(f"Forbidden phrase '{h.phrase}' at {h.path}." for h in scan(blueprint))
    return out
