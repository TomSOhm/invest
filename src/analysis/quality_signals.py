"""
Invest Solo -- Quality Signals
==============================
Pure-function library for the academically rigorous Piotroski F-Score
(Piotroski 2000), sector-aware Altman Z / Z'' (Altman 1968 / 1995/2000),
and Graham Number.

Design principles
-----------------
* No I/O. Every function takes a row dict / pd.Series and returns a number
  or None. Easy to unit-test in isolation.
* NaN-safe: when a required current-year or prior-year input is missing, an
  individual signal returns ``None`` so the aggregator can skip it.
* The aggregator ``piotroski_f_score`` sums non-None signals -- a company
  with 6 of 9 signals available scores 0..6, not 0..9.  This matches
  Piotroski 2000's "data completeness" handling.

Public surface (consumed by ``src/analysis/scoring_engine.py``):
    piotroski_f_score(row) -> int
    altman_z_score(row)    -> float          (delegates to altman_z_select)
    altman_z_classic(row)  -> float
    altman_z_double_prime(row) -> float
    altman_z_select(row)   -> tuple[float, str]
    graham_number(row)     -> float

The 9 individual Piotroski signal helpers are also public so callers / tests
can inspect each component.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Sector dispatch for Altman variants
# ---------------------------------------------------------------------------

# Sectors classified as "manufacturers" for the classic 5-factor Altman Z
# (asset-turnover X5 only makes sense when the firm sells physical product).
_ALTMAN_MANUFACTURER_SECTORS: Set[str] = {
    "Industrials",
    "Materials",
    "Energy",
    "Consumer Cyclical",
    "Consumer Defensive",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# A ``row`` argument may be a plain dict, pd.Series, or any Mapping.
RowLike = Union[Mapping[str, Any], pd.Series]


def _is_finite(val: Any) -> bool:
    """True iff *val* is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    if val is None:
        return False
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


def _get(row: RowLike, key: str, default: Any = np.nan) -> Any:
    """Mapping-agnostic getter.  ``pd.Series.get`` and ``dict.get`` agree on the
    default semantics for missing keys; we just unify the call site here.
    """
    if isinstance(row, pd.Series):
        return row.get(key, default)
    if isinstance(row, Mapping):
        return row.get(key, default)
    # Fallback: attribute access (rare, but harmless).
    return getattr(row, key, default)


def _finite_or_none(val: Any) -> Optional[float]:
    """Coerce *val* to float when finite, else return None."""
    return float(val) if _is_finite(val) else None


# ===========================================================================
# Piotroski F-Score (Piotroski, JAR 2000) -- 9 signals
# ===========================================================================
#
# Each of the 9 signal helpers returns:
#     1   if the signal is present and SATISFIED
#     0   if the signal is present and VIOLATED
#     None if the inputs needed to evaluate the signal are missing
#
# The aggregator ``piotroski_f_score`` simply sums the non-None values.
#
# A company with only 6 of 9 signals computable can therefore score 0..6,
# which is more conservative than awarding silent +1 for missing signals.
# ---------------------------------------------------------------------------


def piotroski_signal_1_roa_positive(row: RowLike) -> Optional[int]:
    """Signal 1 -- Profitability: ROA > 0.

    Returns 1 if current-year ROA is positive, 0 if non-positive, None when
    ROA is unavailable.
    """
    roa = _finite_or_none(_get(row, "ROA"))
    if roa is None:
        return None
    return 1 if roa > 0 else 0


def piotroski_signal_2_cfo_positive(row: RowLike) -> Optional[int]:
    """Signal 2 -- Profitability: Cash From Operations > 0."""
    cfo = _finite_or_none(_get(row, "OperatingCashflow"))
    if cfo is None:
        return None
    return 1 if cfo > 0 else 0


def piotroski_signal_3_delta_roa(row: RowLike) -> Optional[int]:
    """Signal 3 -- Profitability: ROA improved YoY (ROA_t > ROA_{t-1})."""
    roa_now = _finite_or_none(_get(row, "ROA"))
    roa_prior = _finite_or_none(_get(row, "ROA_PriorYear"))
    if roa_now is None or roa_prior is None:
        return None
    return 1 if roa_now > roa_prior else 0


def piotroski_signal_4_accruals(row: RowLike) -> Optional[int]:
    """Signal 4 -- Earnings quality: CFO > Net Income (low accruals).

    Piotroski (2000) compares CFO scaled by total assets against ROA, but the
    sign-only test ``CFO > NetIncome`` is the standard simplification used by
    most replications and is unit-free.
    """
    cfo = _finite_or_none(_get(row, "OperatingCashflow"))
    ni = _finite_or_none(_get(row, "NetIncome"))
    if cfo is None or ni is None:
        return None
    return 1 if cfo > ni else 0


def piotroski_signal_5_delta_leverage(row: RowLike) -> Optional[int]:
    """Signal 5 -- Leverage: Long-term debt decreased YoY (ΔLTD < 0).

    A non-strict tie (ΔLTD == 0) is treated as a non-improvement (=0).
    """
    ltd_now = _finite_or_none(_get(row, "LongTermDebt"))
    ltd_prior = _finite_or_none(_get(row, "LongTermDebt_PriorYear"))
    if ltd_now is None or ltd_prior is None:
        return None
    return 1 if ltd_now < ltd_prior else 0


def piotroski_signal_6_delta_liquidity(row: RowLike) -> Optional[int]:
    """Signal 6 -- Liquidity: Current ratio improved YoY (CR_t > CR_{t-1})."""
    cr_now = _finite_or_none(_get(row, "CurrentRatio"))
    cr_prior = _finite_or_none(_get(row, "CurrentRatio_PriorYear"))
    if cr_now is None or cr_prior is None:
        return None
    return 1 if cr_now > cr_prior else 0


def piotroski_signal_7_no_dilution(row: RowLike) -> Optional[int]:
    """Signal 7 -- Equity issuance: No meaningful dilution.

    The classical test is "no new shares issued in the past year".  We allow
    a 0.5% cushion to absorb stock-based compensation noise.
    """
    shares_now = _finite_or_none(_get(row, "Shares"))
    shares_prior = _finite_or_none(_get(row, "Shares_PriorYear"))
    if shares_now is None or shares_prior is None or shares_prior <= 0:
        return None
    delta = (shares_now - shares_prior) / shares_prior
    return 1 if delta <= 0.005 else 0


def piotroski_signal_8_delta_gross_margin(row: RowLike) -> Optional[int]:
    """Signal 8 -- Operating efficiency: Gross margin improved YoY."""
    gm_now = _finite_or_none(_get(row, "GrossMargin"))
    gm_prior = _finite_or_none(_get(row, "GrossMargin_PriorYear"))
    if gm_now is None or gm_prior is None:
        return None
    return 1 if gm_now > gm_prior else 0


def piotroski_signal_9_delta_asset_turnover(row: RowLike) -> Optional[int]:
    """Signal 9 -- Operating efficiency: Asset turnover improved YoY.

    AT = Revenue / TotalAssets.  If either current or prior period assets are
    non-positive, the signal is undefined (None).
    """
    rev_now = _finite_or_none(_get(row, "Revenue"))
    ta_now = _finite_or_none(_get(row, "TotalAssets"))
    rev_prior = _finite_or_none(_get(row, "Revenue_PriorYear"))
    ta_prior = _finite_or_none(_get(row, "TotalAssets_PriorYear"))
    if any(x is None for x in (rev_now, ta_now, rev_prior, ta_prior)):
        return None
    if ta_now <= 0 or ta_prior <= 0:
        return None
    at_now = rev_now / ta_now
    at_prior = rev_prior / ta_prior
    return 1 if at_now > at_prior else 0


_PIOTROSKI_SIGNALS = (
    piotroski_signal_1_roa_positive,
    piotroski_signal_2_cfo_positive,
    piotroski_signal_3_delta_roa,
    piotroski_signal_4_accruals,
    piotroski_signal_5_delta_leverage,
    piotroski_signal_6_delta_liquidity,
    piotroski_signal_7_no_dilution,
    piotroski_signal_8_delta_gross_margin,
    piotroski_signal_9_delta_asset_turnover,
)


def piotroski_f_score(row: RowLike) -> int:
    """Aggregate the 9 Piotroski signals; sum of present-and-satisfied signals.

    Missing inputs (current-year *or* prior-year NaN) cause the relevant
    signal to be skipped instead of failed.  A company whose data layer
    yields only 6 computable signals will therefore score 0..6, not 0..9.
    """
    total = 0
    for sig in _PIOTROSKI_SIGNALS:
        v = sig(row)
        if v is not None:
            total += int(v)
    return total


# ===========================================================================
# Altman Z-Score (Altman 1968) -- classic 5-factor
# ===========================================================================
#
# Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5
# where:
#   X1 = Working Capital / Total Assets  (= (CurrentAssets - CurrentLiab) / TA)
#   X2 = Retained Earnings / Total Assets
#   X3 = EBIT / Total Assets
#   X4 = Market Value of Equity / Book Value of Total Liabilities
#   X5 = Sales / Total Assets
#
# Zones (manufacturers):
#   Safe     > 2.99
#   Grey     1.81 .. 2.99
#   Distress < 1.81
# ---------------------------------------------------------------------------


def _altman_x_factors(row: RowLike) -> Optional[Tuple[float, float, float, float, float]]:
    """Build the five X factors common to Z and Z''. Returns None on missing data."""
    ta = _finite_or_none(_get(row, "TotalAssets"))
    eq = _finite_or_none(_get(row, "TotalEquity"))
    rev = _finite_or_none(_get(row, "Revenue"))
    ebit = _finite_or_none(_get(row, "EBIT"))
    mktcap = _finite_or_none(_get(row, "MarketCap"))
    current_assets = _finite_or_none(_get(row, "CurrentAssets"))
    current_liabilities = _finite_or_none(_get(row, "CurrentLiabilities"))
    retained_earnings = _finite_or_none(_get(row, "RetainedEarnings"))

    if ta is None or ta <= 0:
        return None
    if current_assets is None or current_liabilities is None:
        return None
    if retained_earnings is None:
        return None
    if ebit is None:
        return None
    if mktcap is None or eq is None:
        return None

    total_liab = ta - eq
    if total_liab <= 0:
        # Negative book liabilities is undefined; skip rather than fabricate.
        return None

    x1 = (current_assets - current_liabilities) / ta
    x2 = retained_earnings / ta
    x3 = ebit / ta
    x4 = mktcap / total_liab
    x5 = (rev / ta) if (rev is not None) else float("nan")

    return x1, x2, x3, x4, x5


def altman_z_classic(row: RowLike) -> float:
    """Classic 5-factor Altman Z (manufacturers).

    Returns NaN if any required input is missing or if the firm has
    non-positive book liabilities (where X4 is undefined).
    """
    factors = _altman_x_factors(row)
    if factors is None:
        return float("nan")
    x1, x2, x3, x4, x5 = factors
    if not _is_finite(x5):
        return float("nan")
    return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5


def altman_z_double_prime(row: RowLike) -> float:
    """4-factor Altman Z'' for non-manufacturers (services, tech, retail, etc.).

    Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4
    Zones:
        Safe     > 2.6
        Grey     1.1 .. 2.6
        Distress < 1.1
    """
    factors = _altman_x_factors(row)
    if factors is None:
        return float("nan")
    x1, x2, x3, x4, _x5 = factors
    return 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4


def altman_z_select(row: RowLike) -> Tuple[float, str]:
    """Pick the right Altman variant based on the row's Sector.

    Returns a tuple ``(score, variant)`` where variant is one of
    ``"classic"`` or ``"double_prime"``.

    The variant is informational -- callers that previously expected a single
    float (M1 ``altman_z_score``) can keep using ``score`` and ignore variant.
    """
    sector = _get(row, "Sector", "")
    is_manufacturer = bool(sector) and sector in _ALTMAN_MANUFACTURER_SECTORS
    if is_manufacturer:
        return altman_z_classic(row), "classic"
    return altman_z_double_prime(row), "double_prime"


def altman_z_score(row: RowLike) -> float:
    """Backwards-compatible single-float Altman wrapper used by the scoring engine.

    Equivalent to ``altman_z_select(row)[0]``.
    """
    return altman_z_select(row)[0]


# ===========================================================================
# Graham Number (kept verbatim from M1)
# ===========================================================================


def graham_number(row: RowLike) -> float:
    """Graham Number = sqrt(22.5 * EPS * BVPS).

    Returns NaN when EPS or BVPS would be non-positive (i.e. when the
    Graham formula is undefined).
    """
    ni = _get(row, "NetIncome", 0)
    shares = _get(row, "Shares", 0)
    eq = _get(row, "TotalEquity", 0)

    # ``shares <= 0`` etc. needs to handle non-numeric / NaN gracefully
    try:
        ni_f = float(ni) if _is_finite(ni) else 0.0
        shares_f = float(shares) if _is_finite(shares) else 0.0
        eq_f = float(eq) if _is_finite(eq) else 0.0
    except (TypeError, ValueError):
        return float("nan")

    if shares_f <= 0 or ni_f <= 0 or eq_f <= 0:
        return float("nan")

    eps = ni_f / shares_f
    bvps = eq_f / shares_f
    return float(np.sqrt(22.5 * eps * bvps))


__all__ = [
    # Piotroski signals
    "piotroski_signal_1_roa_positive",
    "piotroski_signal_2_cfo_positive",
    "piotroski_signal_3_delta_roa",
    "piotroski_signal_4_accruals",
    "piotroski_signal_5_delta_leverage",
    "piotroski_signal_6_delta_liquidity",
    "piotroski_signal_7_no_dilution",
    "piotroski_signal_8_delta_gross_margin",
    "piotroski_signal_9_delta_asset_turnover",
    "piotroski_f_score",
    # Altman
    "altman_z_classic",
    "altman_z_double_prime",
    "altman_z_select",
    "altman_z_score",
    # Graham
    "graham_number",
]
