"""Channel Opportunity Score (CHANNEL_DISCOVERY_SPEC §2) — computed in code, never by a model.

score = Σ(wᵢ·vᵢ) / Σwᵢ with vᵢ ∈ [0, 100]. A criterion with LOW confidence and no evidence counts at
half weight (uncertainty penalty). If more than 30 % of the weight rests on LOW-confidence criteria
the score carries a ±10 band. Weights are 0–15: owner weights are 0–10, and the built-in profiles
multiply some defaults by 1.5.

Evidence rule (§3 step 3, §9): a criterion whose confidence is not LOW must cite at least one source
document that exists. Citations of unknown documents are dropped; a criterion left without
evidence is downgraded to LOW with a note, so the score never rests on an uncited claim.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CRITERIA: dict[str, float] = {
    "AUDIENCE_DEMAND": 8,
    "SEARCH_INTEREST": 6,
    "RISING_TOPICS": 5,
    "EVERGREEN": 7,
    "COMPETITION_LEVEL": 4,
    "ADVERTISER_SUITABILITY": 6,
    "PRODUCTION_FEASIBILITY": 9,
    "ORIGINALITY_OPPORTUNITY": 9,
    "LONG_FORM_POTENTIAL": 5,
    "SHORTS_POTENTIAL": 4,
    "INAUTHENTIC_RISK_INVERSE": 10,
}
PROFILES: dict[str, dict[str, float]] = {
    "Balanced": dict(CRITERIA),
    "Originality-first": {
        **CRITERIA,
        "ORIGINALITY_OPPORTUNITY": CRITERIA["ORIGINALITY_OPPORTUNITY"] * 1.5,
        "INAUTHENTIC_RISK_INVERSE": CRITERIA["INAUTHENTIC_RISK_INVERSE"] * 1.5,
    },
    "Low effort on H-LITE": {
        **CRITERIA,
        "PRODUCTION_FEASIBILITY": CRITERIA["PRODUCTION_FEASIBILITY"] * 1.5,
    },
    # Owner goal (2026-11-12): steady ad income from long-lasting views. Ad income needs YPP, so the
    # inauthentic-content guard stays heavy; Shorts and rising topics help early reach but earn less.
    "Evergreen ad revenue": {
        "AUDIENCE_DEMAND": 12,
        "SEARCH_INTEREST": 11,
        "RISING_TOPICS": 6,
        "EVERGREEN": 15,
        "COMPETITION_LEVEL": 6,
        "ADVERTISER_SUITABILITY": 14,
        "PRODUCTION_FEASIBILITY": 8,
        "ORIGINALITY_OPPORTUNITY": 9,
        "LONG_FORM_POTENTIAL": 11,
        "SHORTS_POTENTIAL": 5,
        "INAUTHENTIC_RISK_INVERSE": 12,
    },
}
DEFAULT_PROFILE = "Evergreen ad revenue"
STRENGTH_MIN = 65
WATCH_MAX = 50
WATCH_MIN_WEIGHT = 8.0
MAX_WEIGHT = 15.0
LOW_PENALTY = 0.5
BAND_SHARE = 0.30
BAND = Decimal("10.0")
FOOTER = "Estimates based on cited sources. Not a prediction of views, subscribers or earnings."
CONFIDENCE = ("LOW", "MEDIUM", "HIGH")
_FEASIBILITY = re.compile(r"^PRODUCTION_FEASIBILITY(_[A-Z0-9-]+)?$")


def normalise_code(code: str) -> str | None:
    code = str(code).strip().upper()
    if _FEASIBILITY.match(code):
        return "PRODUCTION_FEASIBILITY"
    return code if code in CRITERIA else None


def check_weights(weights: Mapping[str, Any]) -> dict[str, float]:
    """Known codes only, each 0–15. Missing codes keep their default weight."""
    out = dict(CRITERIA)
    for code, value in weights.items():
        norm = normalise_code(code)
        if norm is None:
            raise ValueError(f"Unknown criterion '{code}'.")
        try:
            w = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Weight for {norm} must be a number.") from exc
        if not 0 <= w <= MAX_WEIGHT:
            raise ValueError(f"Weight for {norm} must be between 0 and {MAX_WEIGHT:g}.")
        out[norm] = w
    return out


@dataclass(frozen=True)
class Score:
    value: Decimal
    band: Decimal | None
    low_weight_share: float


def _effective(c: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    w = float(weights.get(str(c["code"]), CRITERIA.get(str(c["code"]), 0)))
    if c.get("confidence") == "LOW" and not c.get("evidence"):
        w *= LOW_PENALTY
    return w


def score(criteria: list[dict[str, Any]], weights: Mapping[str, float]) -> Score:
    total = weighted = low = 0.0
    for c in criteria:
        w = _effective(c, weights)
        total += w
        weighted += w * float(c["value"])
        if c.get("confidence") == "LOW":
            low += w
    if total == 0:
        return Score(Decimal("0.00"), None, 0.0)
    value = Decimal(str(weighted / total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    share = low / total
    return Score(value, BAND if share > BAND_SHARE else None, round(share, 4))


def remarks(criteria: list[dict[str, Any]], weights: Mapping[str, float]) -> list[dict[str, Any]]:
    """Why a niche scored as it did, under the current weights (deterministic, no AI).

    Up to 3 strengths (value >= 65, ranked by weight x value) and up to 2 things to watch: an
    important criterion (weight >= 8) that is weak (< 50) or rests on little evidence (LOW).
    """

    def w(c: Mapping[str, Any]) -> float:
        return float(weights.get(str(c["code"]), CRITERIA.get(str(c["code"]), 0)))

    strong = sorted(
        (c for c in criteria if int(c["value"]) >= STRENGTH_MIN and w(c) > 0),
        key=lambda c: (-w(c) * int(c["value"]), str(c["code"])),
    )[:3]
    weak = sorted(
        (
            c
            for c in criteria
            if w(c) >= WATCH_MIN_WEIGHT and (int(c["value"]) < WATCH_MAX or c.get("confidence") == "LOW")
        ),
        key=lambda c: (-w(c), int(c["value"]), str(c["code"])),
    )[:2]
    return [
        {
            "kind": kind,
            "code": str(c["code"]),
            "value": int(c["value"]),
            "confidence": c.get("confidence", "LOW"),
        }
        for kind, group in (("STRENGTH", strong), ("WATCH", weak))
        for c in group
    ]


def apply_weights(criteria: list[dict[str, Any]], weights: Mapping[str, float]) -> list[dict[str, Any]]:
    """Copy of the criteria with each one's current weight recorded (for the breakdown table)."""
    return [{**c, "weight": float(weights.get(str(c["code"]), CRITERIA[str(c["code"])]))} for c in criteria]


@dataclass(frozen=True)
class DocRef:
    url: str
    title: str | None


def validate_criteria(raw: list[dict[str, Any]], docs: Mapping[str, DocRef]) -> list[dict[str, Any]]:
    """Normalise a model's criteria and enforce the evidence rule."""
    seen: dict[str, dict[str, Any]] = {}
    for item in raw:
        code = normalise_code(str(item.get("code", "")))
        if code is None or code in seen:
            continue
        try:
            value = max(0, min(100, int(item.get("value", 0))))
        except (TypeError, ValueError):
            continue
        evidence = []
        for ev in item.get("evidence") or []:
            doc_id = str(ev.get("source_document_id", ""))
            ref = docs.get(doc_id)
            if ref is not None:
                evidence.append(
                    {
                        "source_document_id": doc_id,
                        "url": ref.url,
                        "title": ref.title,
                        "quote": str(ev.get("quote", ""))[:300],
                    }
                )
        confidence = item.get("confidence") if item.get("confidence") in CONFIDENCE else "LOW"
        note = str(item.get("note") or "")[:200] or None
        if confidence != "LOW" and not evidence:
            confidence = "LOW"
            note = "Downgraded to LOW: no cited source document was found."
        seen[code] = {
            "code": code,
            "value": value,
            "evidence": evidence,
            "confidence": confidence,
            "note": note,
        }
    return list(seen.values())
