"""Pure functions deriving Momentum-feeding signals from yfinance.analysis data.

Signals
-------
- **SUE** (Standardized Unexpected Earnings): ``surprises[0] / stdev(surprises[1:], ddof=1)``.
  Current quarter is excluded from the stdev denominator per Bernard & Thomas (1989).
  Dollar surprises (``eps_actual - eps_estimate``), NOT ``surprisePercent``.
  Requires at least 6 quarters; returns ``None`` otherwise.

  References:
    Foster, Olsen, Shevlin (1984). "Earnings Releases, Anomalies, and the
    Behavior of Security Returns." *The Accounting Review*.
    Bernard, V.L. & Thomas, J.K. (1989). "Post-Earnings-Announcement Drift:
    Delayed Price Response or Risk Premium?" *Journal of Accounting Research*.
    Livnat, J. & Mendenhall, R.R. (2006). *Journal of Accounting Research*.

- **EPS revision %** over N days: ``(current - estimate_N_days_ago) /
  abs(estimate_N_days_ago)``. ``abs()`` preserves sign when prior estimate
  is negative (loss-period revisions). Source: tk.eps_trend.

  References:
    Stickel (1991). "Common Stock Returns Surrounding Earnings Forecast
    Revisions." *The Accounting Review*.
    Womack (1996). *Journal of Finance*.

This module has zero I/O. It operates on yfinance-derived dicts/lists
already in memory.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# Phase 0 financial review: 6 minimum, 8 (Bernard-Thomas) maximum.
_SUE_MIN_QUARTERS = 6
_SUE_MAX_QUARTERS = 8


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def compute_sue_from_history(
    earnings_history: list[dict[str, Any]],
) -> float | None:
    """Compute SUE from a list of {eps_actual, eps_estimate} rows.

    Most-recent quarter first. Returns ``None`` when fewer than 6 valid rows
    are available (Bernard-Thomas minimum) or when σ ≤ 0.
    """
    surprises: list[float] = []
    for row in earnings_history[:_SUE_MAX_QUARTERS]:
        a = _f(row.get("eps_actual"))
        e = _f(row.get("eps_estimate"))
        if a is None or e is None:
            continue
        surprises.append(a - e)
    if len(surprises) < _SUE_MIN_QUARTERS:
        return None
    # Exclude the current quarter from σ to avoid forward-looking bias.
    sigma_arr = np.array(surprises[1:], dtype=float)
    sd = float(sigma_arr.std(ddof=1))
    if sd <= 0:
        return None
    return float(surprises[0] / sd)


def compute_eps_revision_pct_from_trend(
    trend: list[dict[str, Any]],
    days: int,
) -> float | None:
    """Percent change in the current quarter's EPS estimate vs N days ago.

    ``trend`` rows are produced by YFinanceDataFetcher.fetch_eps_trend with
    keys ``current``, ``n_minus_7d``, ``n_minus_30d``, ``n_minus_60d``,
    ``n_minus_90d``. Picks the first row (current quarter).
    """
    if not trend:
        return None
    row = trend[0]
    key = f"n_minus_{days}d"
    cur = _f(row.get("current"))
    past = _f(row.get(key))
    if cur is None or past is None or past == 0:
        return None
    return (cur - past) / abs(past)


def parse_recommendations_summary(
    rec: dict[str, Any] | None,
) -> dict[str, int]:
    """Pass-through normalizer producing the standard 5-key shape."""
    out = {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
    if not rec:
        return out
    for key in out:
        val = rec.get(key)
        if isinstance(val, (int, float)) and not math.isnan(float(val)):
            out[key] = int(val)
    return out


def earnings_surprise_latest(
    earnings_history: list[dict[str, Any]],
) -> float | None:
    """Return the latest quarter's surprise %, or None when unavailable."""
    if not earnings_history:
        return None
    return _f(earnings_history[0].get("surprise_pct"))
