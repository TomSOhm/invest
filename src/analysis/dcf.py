"""
Invest Solo — Two-stage DCF with sensitivity grid (M6).

Pure-function library, no I/O. NaN-safe and tolerant of partial data.

Approach
--------
* WACC via CAPM cost-of-equity + after-tax cost-of-debt blend
* 5-year explicit FCF projection (revenue * FCF_margin, revenue grows by
  a 5-period glide path)
* Gordon-growth terminal value
* Equity value = sum(discounted FCFs) + discounted TV − net debt
* Per-share intrinsic = equity value / shares outstanding
* Sensitivity grid: WACC ±1pp, TGR ±50bp -> 3x3 = 9 cells
* Margin of safety vs. price:  (intrinsic − price) / price
    -> positive when intrinsic > price (undervalued)
    -> negative when intrinsic < price (overvalued)

Glide path
----------
If a caller does not supply an explicit ``revenue_growth_glide`` array,
``build_revenue_glide`` linearly fades the current YoY growth rate toward
the long-run terminal growth over 5 years. This avoids Damodaran's "fat
tail" problem (perpetual high-teens growth) for fast growers while still
honouring near-term momentum.

All public functions return NaN (or NaN-filled dicts) when inputs are
incomplete. Callers should NOT rely on exceptions — check ``warnings``
in ``dcf_with_sensitivity``'s output instead.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np


__all__ = [
    "compute_wacc",
    "build_revenue_glide",
    "project_fcf",
    "terminal_value",
    "intrinsic_value_per_share",
    "dcf_with_sensitivity",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _is_finite(val: Any) -> bool:
    """True iff ``val`` is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _to_float(val: Any, default: float = float("nan")) -> float:
    """Coerce to float; return default if input is missing/invalid."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return f


# ──────────────────────────────────────────────────────────────────────────────
# WACC
# ──────────────────────────────────────────────────────────────────────────────


def compute_wacc(
    beta: float,
    market_cap: float,
    total_debt: float,
    tax_rate: float = 0.25,
    risk_free_rate: float = 0.03,
    equity_risk_premium: float = 0.055,
    cost_of_debt: float = 0.05,
) -> float:
    """Weighted average cost of capital.

    ``WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)`` with ``Re = Rf + Beta * ERP``.

    Parameters
    ----------
    beta : float
        Equity beta (typically yfinance ``beta`` field).
    market_cap : float
        Equity market capitalisation (E).
    total_debt : float
        Book value of total debt (proxy for D — Damodaran uses market value
        of debt where available, but book value is a reasonable approximation
        for non-distressed issuers).
    tax_rate : float, default 0.25
        Effective marginal tax rate. Used for the after-tax cost of debt.
    risk_free_rate : float, default 0.03
        10-year sovereign yield (FR OAT for PEA, US 10y for global).
    equity_risk_premium : float, default 0.055
        Damodaran ERP estimate (developed-markets baseline ~5.5%).
    cost_of_debt : float, default 0.05
        Pre-tax cost of debt. Default approximates investment-grade
        corporate yields (M9 could refine via FMP credit spread).

    Returns
    -------
    float
        WACC as a decimal (e.g. 0.085 = 8.5%). Returns ``NaN`` if any required
        input is missing or invalid, or if E + D <= 0 (capital structure
        undefined).
    """
    beta_f = _to_float(beta)
    mc = _to_float(market_cap)
    td = _to_float(total_debt, default=0.0)  # zero-debt is a valid edge case
    tx = _to_float(tax_rate, default=0.25)
    rf = _to_float(risk_free_rate, default=0.03)
    erp = _to_float(equity_risk_premium, default=0.055)
    cod = _to_float(cost_of_debt, default=0.05)

    if not (_is_finite(beta_f) and _is_finite(mc) and mc > 0):
        return float("nan")
    # Negative debt is non-physical
    if td < 0:
        return float("nan")

    v = mc + td
    if v <= 0:
        return float("nan")

    re = rf + beta_f * erp
    e_weight = mc / v
    d_weight = td / v

    wacc = e_weight * re + d_weight * cod * (1.0 - tx)
    if not math.isfinite(wacc):
        return float("nan")
    return wacc


# ──────────────────────────────────────────────────────────────────────────────
# Revenue glide path
# ──────────────────────────────────────────────────────────────────────────────


def build_revenue_glide(
    near_term_growth: float,
    terminal_growth: float = 0.025,
    n_years: int = 5,
) -> List[float]:
    """Linearly fade ``near_term_growth`` toward ``terminal_growth`` over n years.

    The first year uses ``near_term_growth`` (clamped at ±50%); the last
    year approaches ``terminal_growth``. This is the textbook two-stage DCF
    glide path: explicit-period growth converges to the perpetuity rate.

    Returns a list of length ``n_years``. If ``near_term_growth`` is NaN,
    every year is set to ``terminal_growth`` (conservative fallback).
    """
    g = _to_float(near_term_growth)
    tg = _to_float(terminal_growth, default=0.025)
    n = max(int(n_years), 1)

    if not _is_finite(g):
        return [tg] * n

    # Clamp absurd inputs (e.g. yfinance returning 250% revenue growth on
    # an SPAC's first year). Keeps the model well-behaved without silently
    # ignoring the signal.
    g = max(min(g, 0.50), -0.50)

    if n == 1:
        return [g]
    # Linear glide from g (year 1) to tg (year n).
    step = (tg - g) / (n - 1)
    return [g + step * i for i in range(n)]


# ──────────────────────────────────────────────────────────────────────────────
# FCF projection
# ──────────────────────────────────────────────────────────────────────────────


def project_fcf(
    fcf_t0: float,
    revenue_growth_glide: List[float],
    fcf_margin: float,
    revenue_t0: float,
) -> np.ndarray:
    """Project ``len(revenue_growth_glide)`` years of free cash flow.

    Approach: revenue compounds by ``revenue_growth_glide``;
    FCF_t = Revenue_t * fcf_margin.

    Why use ``fcf_margin`` rather than growing FCF directly?  Because FCF
    is more volatile than revenue (capex cycles, working-capital swings),
    and the Damodaran convention is to anchor projections to the more
    stable top-line then apply a normalised conversion ratio.

    Parameters
    ----------
    fcf_t0 : float
        Trailing-twelve-month FCF. Used only when ``revenue_t0`` is missing
        AND ``fcf_margin`` is not derivable (no longer triggered in current
        impl — kept in signature for forward compatibility).
    revenue_growth_glide : list of float
        n-period growth rates (e.g. 5 values for the standard 5-year stage).
    fcf_margin : float
        Steady-state FCF / Revenue ratio.
    revenue_t0 : float
        Latest annual revenue (Revenue field).

    Returns
    -------
    np.ndarray
        Shape (n,). NaN-filled if revenue or fcf_margin is missing.
    """
    n = len(revenue_growth_glide)
    rev = _to_float(revenue_t0)
    margin = _to_float(fcf_margin)

    if not _is_finite(rev) or rev <= 0:
        # Fall back to projecting fcf_t0 directly via the growth glide.
        f0 = _to_float(fcf_t0)
        if not _is_finite(f0):
            return np.full(n, np.nan, dtype=float)
        out = np.empty(n, dtype=float)
        running = f0
        for i, g in enumerate(revenue_growth_glide):
            running = running * (1.0 + (_to_float(g, default=0.0)))
            out[i] = running
        return out

    if not _is_finite(margin):
        return np.full(n, np.nan, dtype=float)

    out = np.empty(n, dtype=float)
    running_rev = rev
    for i, g in enumerate(revenue_growth_glide):
        gf = _to_float(g, default=0.0)
        running_rev = running_rev * (1.0 + gf)
        out[i] = running_rev * margin
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Terminal value
# ──────────────────────────────────────────────────────────────────────────────


def terminal_value(
    fcf_year_5: float,
    wacc: float,
    terminal_growth_rate: float,
) -> float:
    """Gordon-growth terminal value.

    ``TV = FCF_n * (1 + g) / (WACC - g)``

    Returns NaN if:
      - any input is non-finite
      - ``WACC <= terminal_growth_rate`` (Gordon model invalid; would
        yield negative or infinite TV)
    """
    fcf = _to_float(fcf_year_5)
    w = _to_float(wacc)
    g = _to_float(terminal_growth_rate)
    if not (_is_finite(fcf) and _is_finite(w) and _is_finite(g)):
        return float("nan")
    if w <= g:
        return float("nan")
    return fcf * (1.0 + g) / (w - g)


# ──────────────────────────────────────────────────────────────────────────────
# Per-share intrinsic value
# ──────────────────────────────────────────────────────────────────────────────


def intrinsic_value_per_share(
    fcf_proj: np.ndarray,
    tv: float,
    wacc: float,
    shares_out: float,
    net_debt: float,
) -> float:
    """Discount projected FCFs + TV at WACC, deduct net debt, divide by shares.

    EV = Σ FCF_t / (1+WACC)^t  +  TV / (1+WACC)^n
    Equity = EV − net_debt
    Per share = Equity / shares_out

    Returns NaN if any required input is invalid OR if shares_out <= 0.
    Negative per-share values are NOT clipped — a deeply distressed firm
    can produce a negative equity value and this should propagate.
    """
    if fcf_proj is None or len(fcf_proj) == 0:
        return float("nan")
    w = _to_float(wacc)
    s = _to_float(shares_out)
    nd = _to_float(net_debt, default=0.0)
    t_v = _to_float(tv)
    if not (_is_finite(w) and _is_finite(s) and _is_finite(t_v)):
        return float("nan")
    if s <= 0:
        return float("nan")
    if not (1.0 + w) > 0:
        return float("nan")

    n = len(fcf_proj)
    discount_factors = np.array([(1.0 + w) ** (i + 1) for i in range(n)], dtype=float)
    fcf_arr = np.asarray(fcf_proj, dtype=float)
    if np.any(~np.isfinite(fcf_arr)):
        return float("nan")

    pv_fcf = float(np.sum(fcf_arr / discount_factors))
    pv_tv = t_v / ((1.0 + w) ** n)
    enterprise_value = pv_fcf + pv_tv
    equity_value = enterprise_value - nd
    return equity_value / s


# ──────────────────────────────────────────────────────────────────────────────
# Full DCF with sensitivity grid
# ──────────────────────────────────────────────────────────────────────────────


_DEFAULT_DCF_SETTINGS: Dict[str, float] = {
    "projection_years": 5,
    "terminal_growth_rate": 0.025,
    "risk_free_rate": 0.03,
    "equity_risk_premium": 0.055,
    "tax_rate_default": 0.25,
}


def _resolve_settings(settings: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Merge caller-supplied DCF settings (e.g. ``settings.yaml`` ``valuation.dcf`` block)
    with the module-level defaults. Caller wins on conflict.
    """
    out = dict(_DEFAULT_DCF_SETTINGS)
    if settings:
        for k in (
            "projection_years",
            "terminal_growth_rate",
            "risk_free_rate",
            "equity_risk_premium",
            "tax_rate_default",
        ):
            if k in settings and _is_finite(settings[k]):
                out[k] = float(settings[k])
    return out


def dcf_with_sensitivity(
    inputs: Dict[str, Any],
    wacc_delta: float = 0.01,
    tgr_delta: float = 0.005,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Two-stage DCF with a 3x3 WACC × TGR sensitivity grid.

    Parameters
    ----------
    inputs : dict
        Row-style input dict. Required-ish keys (all optional, but the
        more present, the more meaningful the output):

        - ``Beta``, ``MarketCap``, ``TotalDebt``, ``Cash``, ``Shares``
        - ``FCF``, ``Revenue``, ``FCFMargin``
        - ``RevenueGrowth`` (current YoY)
        - ``Price`` (used for margin-of-safety calculation)

        Optional keys:
        - ``RevenueGlide`` : explicit 5-element list overriding the auto
          glide derived from ``RevenueGrowth``.
        - ``CostOfDebt`` : override the 5% default (e.g. fed by FMP).

    wacc_delta : float, default 0.01
        Half-width for WACC sensitivity (so grid spans WACC±wacc_delta).

    tgr_delta : float, default 0.005
        Half-width for terminal-growth sensitivity.

    settings : dict, optional
        Forwarded ``settings.yaml`` ``valuation.dcf`` block. When omitted,
        module defaults apply.

    Returns
    -------
    dict
        Always returns a dict with these keys (NaN where data is missing):

        - ``wacc_base``, ``tgr_base`` : centre-cell parameters
        - ``intrinsic_low``, ``intrinsic_mid``, ``intrinsic_high`` : per-share
        - ``mos_low``, ``mos_mid``, ``mos_high`` : margin of safety vs. ``Price``
        - ``scenarios`` : 9-cell {label -> intrinsic_value}, e.g. ``"wacc-tgr+"``
        - ``warnings`` : list of free-text issues encountered

    Notes
    -----
    Margin of safety convention:
        mos = (intrinsic − price) / price
        > 0  ⇒  undervalued  (e.g. 0.30 = price is 70% of intrinsic)
        < 0  ⇒  overvalued   (e.g. -0.30 = price is 130% of intrinsic)

    This is the convention activated by SIGNAL_THRESHOLDS in M6.
    """
    cfg = _resolve_settings(settings)
    warnings: List[str] = []

    nan_result: Dict[str, Any] = {
        "wacc_base": float("nan"),
        "tgr_base": float(cfg["terminal_growth_rate"]),
        "intrinsic_low": float("nan"),
        "intrinsic_mid": float("nan"),
        "intrinsic_high": float("nan"),
        "mos_low": float("nan"),
        "mos_mid": float("nan"),
        "mos_high": float("nan"),
        "scenarios": {},
        "warnings": warnings,
    }

    # ---------- Pull inputs (NaN-safe) ----------
    beta = _to_float(inputs.get("Beta"))
    market_cap = _to_float(inputs.get("MarketCap"))
    total_debt = _to_float(inputs.get("TotalDebt"), default=0.0)
    cash = _to_float(inputs.get("Cash"), default=0.0)
    shares = _to_float(inputs.get("Shares"))
    revenue = _to_float(inputs.get("Revenue"))
    fcf = _to_float(inputs.get("FCF"))
    fcf_margin = _to_float(inputs.get("FCFMargin"))
    revenue_growth = _to_float(inputs.get("RevenueGrowth"))
    price = _to_float(inputs.get("Price"))
    cost_of_debt = _to_float(inputs.get("CostOfDebt"), default=0.05)

    # If FCFMargin is missing but FCF and Revenue are present, derive it.
    if not _is_finite(fcf_margin) and _is_finite(fcf) and _is_finite(revenue) and revenue > 0:
        fcf_margin = fcf / revenue

    # Bail-outs: each accumulates a warning instead of throwing.
    if not _is_finite(beta) or not _is_finite(market_cap) or market_cap <= 0:
        warnings.append("Insufficient capital-structure data (need Beta, MarketCap > 0)")
        return nan_result
    if not _is_finite(shares) or shares <= 0:
        warnings.append("Shares outstanding missing or non-positive")
        return nan_result
    if not _is_finite(revenue) or revenue <= 0:
        warnings.append("Revenue missing or non-positive")
        return nan_result
    if not _is_finite(fcf_margin):
        warnings.append("FCF margin not derivable (need FCFMargin or FCF+Revenue)")
        return nan_result
    if fcf_margin <= 0:
        warnings.append(
            f"Non-positive FCF margin ({fcf_margin:.3f}); DCF assumes positive future cash flows"
        )
        # We continue: the grid will compute (negative) values that still
        # convey the directional message "this firm doesn't generate cash".

    # ---------- WACC ----------
    wacc_base = compute_wacc(
        beta=beta,
        market_cap=market_cap,
        total_debt=total_debt,
        tax_rate=cfg["tax_rate_default"],
        risk_free_rate=cfg["risk_free_rate"],
        equity_risk_premium=cfg["equity_risk_premium"],
        cost_of_debt=cost_of_debt,
    )
    if not _is_finite(wacc_base):
        warnings.append("WACC computation failed")
        return nan_result

    tgr_base = float(cfg["terminal_growth_rate"])

    # ---------- Revenue glide ----------
    glide_override = inputs.get("RevenueGlide")
    if isinstance(glide_override, list) and len(glide_override) >= 1:
        revenue_glide = [
            _to_float(x, default=tgr_base) for x in glide_override
        ]
    else:
        revenue_glide = build_revenue_glide(
            near_term_growth=revenue_growth,
            terminal_growth=tgr_base,
            n_years=5,
        )
        if not _is_finite(revenue_growth):
            warnings.append(
                "RevenueGrowth missing — glide flat at terminal rate (conservative)"
            )

    # ---------- Net debt ----------
    net_debt = total_debt - cash
    if not _is_finite(net_debt):
        net_debt = 0.0

    # ---------- 3x3 sensitivity grid ----------
    wacc_grid = [wacc_base - wacc_delta, wacc_base, wacc_base + wacc_delta]
    tgr_grid = [tgr_base - tgr_delta, tgr_base, tgr_base + tgr_delta]
    wacc_labels = ["wacc-", "wacc", "wacc+"]
    tgr_labels = ["tgr-", "tgr", "tgr+"]

    scenarios: Dict[str, float] = {}
    grid_values: List[float] = []
    mid_value = float("nan")

    invalid_terminal = False

    for wi, w_val in enumerate(wacc_grid):
        for ti, g_val in enumerate(tgr_grid):
            label = f"{wacc_labels[wi]}{tgr_labels[ti]}"
            fcf_proj = project_fcf(
                fcf_t0=fcf,
                revenue_growth_glide=revenue_glide,
                fcf_margin=fcf_margin,
                revenue_t0=revenue,
            )
            tv = terminal_value(
                fcf_year_5=float(fcf_proj[-1]) if len(fcf_proj) and _is_finite(fcf_proj[-1]) else float("nan"),
                wacc=w_val,
                terminal_growth_rate=g_val,
            )
            if not _is_finite(tv):
                invalid_terminal = True
                scenarios[label] = float("nan")
                continue
            iv = intrinsic_value_per_share(
                fcf_proj=fcf_proj,
                tv=tv,
                wacc=w_val,
                shares_out=shares,
                net_debt=net_debt,
            )
            scenarios[label] = iv
            if _is_finite(iv):
                grid_values.append(iv)
            if wi == 1 and ti == 1:
                mid_value = iv

    if invalid_terminal:
        warnings.append("WACC <= TGR in at least one sensitivity cell — terminal model invalid")

    if not grid_values:
        warnings.append("All sensitivity cells produced invalid intrinsic values")
        nan_result["wacc_base"] = wacc_base
        nan_result["scenarios"] = scenarios
        return nan_result

    intrinsic_low = float(min(grid_values))
    intrinsic_high = float(max(grid_values))
    intrinsic_mid = float(mid_value) if _is_finite(mid_value) else float(np.nan)

    # ---------- Margin of safety vs. price ----------
    if _is_finite(price) and price > 0:
        def _mos(iv: float) -> float:
            return (iv - price) / price if _is_finite(iv) else float("nan")

        mos_low = _mos(intrinsic_low)
        mos_mid = _mos(intrinsic_mid)
        mos_high = _mos(intrinsic_high)
    else:
        warnings.append("Price missing — margin of safety not computable")
        mos_low = mos_mid = mos_high = float("nan")

    return {
        "wacc_base": wacc_base,
        "tgr_base": tgr_base,
        "intrinsic_low": intrinsic_low,
        "intrinsic_mid": intrinsic_mid,
        "intrinsic_high": intrinsic_high,
        "mos_low": mos_low,
        "mos_mid": mos_mid,
        "mos_high": mos_high,
        "scenarios": scenarios,
        "warnings": warnings,
    }
