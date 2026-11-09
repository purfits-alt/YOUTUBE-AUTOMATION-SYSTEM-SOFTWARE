"""A32 paid-indicator checks on successful provider responses (COST_CONTROL_SPEC §5).

Error responses with billing wording are caught in the adapters (``PAID_INDICATOR``). Here the
*successful* responses are checked: a rate limit far above the free tier, or a tier field that is
not free, means the key now sits on a paid path.
"""

from __future__ import annotations

from collections.abc import Mapping

from tubeforge.db.models import ProviderRegistry

JUMP_FACTOR = 10  # a published free limit that suddenly appears 10× larger looks like a paid tier


def inspect(provider: ProviderRegistry, headers: Mapping[str, str]) -> str | None:
    h = {k.lower(): v for k, v in headers.items()}
    tier = h.get("x-goog-quota-tier") or h.get("x-usage-tier") or h.get("x-groq-tier")
    if tier and tier.strip().lower() not in {"free", "free tier", "developer-free"}:
        return f"the provider reports usage tier “{tier}”"
    rpd = (provider.limits or {}).get("rpd")
    reported = h.get("x-ratelimit-limit-requests")
    if rpd and reported and reported.isdigit() and int(reported) > JUMP_FACTOR * int(rpd):
        return f"daily request limit {reported} is far above the free {rpd}"
    return None
