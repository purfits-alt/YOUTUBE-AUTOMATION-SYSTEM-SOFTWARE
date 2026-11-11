"""Pageview signals computed in code (CHANNEL_DISCOVERY_SPEC §2 evidence, §5 trend signal).

Models only read these numbers; they never compute or change them.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SeriesMetrics:
    days: int
    avg_daily: float
    last90_avg: float
    prev90_avg: float
    growth_pct: float | None  # last 90 days vs the 90 before; None if there is no earlier window
    variation: float  # coefficient of variation of monthly totals (lower = steadier)
    demand_hint: int  # 0–100, log scale of average daily views
    rising_hint: int  # 0–100, 50 = flat
    evergreen_hint: int  # 0–100, steadiness over the series


def _mean(xs: list[int]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def demand_value(avg_daily: float) -> int:
    """100/day → 20, 1k → 40, 10k → 60, 100k → 80, 1M → 100."""
    if avg_daily <= 0:
        return 0
    return max(0, min(100, round(20 * math.log10(avg_daily) - 20)))


def series_metrics(points: list[tuple[date, int]]) -> SeriesMetrics:
    views = [v for _d, v in sorted(points)]
    last90, prev90 = views[-90:], views[-180:-90]
    growth = None
    if prev90 and _mean(prev90) > 0:
        growth = (_mean(last90) - _mean(prev90)) / _mean(prev90) * 100
    months = [sum(views[i : i + 30]) for i in range(0, len(views) - len(views) % 30, 30)] or [sum(views)]
    mean_m = _mean(months)
    variation = statistics.pstdev(months) / mean_m if len(months) > 1 and mean_m > 0 else 1.0
    rising = 50 if growth is None else max(0, min(100, round(50 + growth / 2)))
    evergreen = max(0, min(100, round(100 * (1 - min(variation, 1.0)))))
    if len(views) < 300:
        evergreen = min(evergreen, 60)  # under ~10 months there is not enough history to call it evergreen
    avg = _mean(views)
    return SeriesMetrics(
        days=len(views),
        avg_daily=round(avg, 1),
        last90_avg=round(_mean(last90), 1),
        prev90_avg=round(_mean(prev90), 1),
        growth_pct=None if growth is None else round(growth, 1),
        variation=round(variation, 3),
        demand_hint=demand_value(avg),
        rising_hint=rising,
        evergreen_hint=evergreen,
    )


def zscore_7d(points: list[tuple[date, int]]) -> float:
    """Last 7 days vs the 28 days before them (§5). 0 when there is not enough data."""
    views = [v for _d, v in sorted(points)]
    if len(views) < 35:
        return 0.0
    recent, base = views[-7:], views[-35:-7]
    sd = statistics.pstdev(base) or 1.0
    return round((_mean(recent) - _mean(base)) / sd, 2)
