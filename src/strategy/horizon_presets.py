"""
Invest Solo — Horizon-Specific Screener Presets (M8)
=====================================================
9 named filter dicts corresponding to the horizon configurations documented
in HORIZON_CONFIGS.md.  Each dict is self-contained and is consumed by
``apply_filters`` in ``screener.py``; the ``screen_horizon_preset`` helper
applies the preset and sorts the output by the matching horizon score.

Preset names / horizons
-----------------------
Long-term  (5y+):
    LT_QUALITY_COMPOUNDER   — default LT; quality at fair price
    LT_PEA_DEFENSIVE        — PEA-strict, lower-vol tilt
    LT_DEEP_VALUE           — contrarian; anti-value-trap gates

Medium-term (1–3y):
    MT_GARP                 — Growth At Reasonable Price; re-rating catalyst
    MT_TURNAROUND           — operational improvement; higher-risk
    MT_INCOME               — yield + sustainability + dividend growth

Short-term  (<6mo):
    ST_MOMENTUM_QUALITY     — academic momentum + quality floor
    ST_EARNINGS_DRIFT       — PEAD: post-earnings announcement drift
    ST_OVERSOLD_BOUNCE      — mean-reversion; Connors RSI(2) extreme oversold

ST presets carry ``recommended_account: "CTO"`` and ``pea_warning: True``
because short-term momentum trading inside a PEA can trigger the frequent-
trading rule that collapses the tax wrapper.

Every preset embeds the universal pre-filters (§0 from HORIZON_CONFIGS.md):
    min_market_cap          €100M  (ST: €500M)
    min_avg_daily_volume    €500k  (actual column: AvgVolume in the scorer)
    min_years_listed        3
    not_in_distress         True   (Altman Z'' / Z ≥ 1.1)
    min_data_completeness   0.70

Where a filter depends on a column not yet plumbed into the data layer
(e.g. RSI_2, forward P/E, operational margin improvement), the preset
documents the missing dependency in a ``requires`` list.  ``apply_filters``
is written to silently skip any filter key whose target column is absent
from the DataFrame — "skipped, not errored" semantics are critical so adding
a new column incrementally never breaks existing runs.

Usage
-----
>>> from src.strategy.horizon_presets import PRESET_REGISTRY, get_preset
>>> from src.strategy.horizon_presets import screen_horizon_preset, list_presets
>>> list_presets()
>>> filtered_df = screen_horizon_preset(df, "LT_QUALITY_COMPOUNDER")
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# Internal type alias
# ──────────────────────────────────────────────────────────────────────────────

_PresetDict = dict[str, Any]

# ──────────────────────────────────────────────────────────────────────────────
# Universal pre-filter block
# Applied to every preset.  Values come from HORIZON_CONFIGS.md §0.
# ──────────────────────────────────────────────────────────────────────────────

_UNIVERSAL_PREFILTERS: dict[str, Any] = {
    # Liquidity floor — avoid manipulation and noise (€100M market cap)
    "min_market_cap": 100_000_000,
    # Daily traded value floor (volume × price); column AvgVolume in scorer
    "min_avg_daily_volume_eur": 500_000,
    # Ensures multi-year metrics are available (no IPO honeymoon)
    "min_years_listed": 3,
    # Universal ESG/sector exclusions loaded from settings.yaml at runtime
    "exclude_sectors": ["Tobacco", "Gambling", "Coal_Mining"],
    # Altman Z'' / Z ≥ 1.1 — drop distressed names
    "not_in_distress": True,
    # Skip tickers where >30% of scoring inputs are NaN
    "min_data_completeness": 0.70,
}

# ──────────────────────────────────────────────────────────────────────────────
# 1. LT_QUALITY_COMPOUNDER — default long-term preset
# ──────────────────────────────────────────────────────────────────────────────

LT_QUALITY_COMPOUNDER: _PresetDict = {
    "horizon": "long_term",
    "name": "LT Quality Compounder",
    "description": (
        "Buy great businesses at fair prices; hold for compounding. "
        "Tax-optimal in PEA. Combines a ROIC floor, F-Score ≥ 7, "
        "DCF margin of safety, and sector-relative valuation cap."
    ),
    # Columns not yet plumbed (present in plan, absent from data fetcher as of M8).
    # apply_filters silently skips these keys when the column is absent.
    "requires": [
        "GrossMargin_Stddev_5y",  # max_gross_margin_stddev_5y
        "RevenueCAGR_5y",  # min_revenue_cagr_5y, max_revenue_cagr_5y
        "EPS_CAGR_5y",  # min_eps_cagr_5y
        "PosRevenueYears_5y",  # min_pos_revenue_years_5y
        "TotalShareholderYield",  # min_total_shareholder_yield
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **_UNIVERSAL_PREFILTERS,
        # LT uses a stricter data-completeness threshold than the ST horizon
        "min_data_completeness": 0.80,
        # ── Quality / Profitability ───────────────────────────────────────
        "min_roic": 0.12,  # 12% ROIC (above WACC for most names)
        "min_roic_5y_avg": 0.10,  # Sustained, not a one-off
        "min_gross_profitability": 0.20,  # GP / Total Assets (Novy-Marx)
        "max_gross_margin_stddev_5y": 0.05,  # 5pp = stable pricing power
        "min_fcf_margin": 0.05,  # Cash-generative
        "min_ccr_3y_avg": 0.70,  # FCF / NI: earnings quality
        "min_f_score": 7,  # 7+ on real (not proxied) F-Score
        # ── Financial Health ──────────────────────────────────────────────
        "min_altman_z": 2.6,  # Safe zone (Z'' for non-manufacturers)
        "max_nd_ebitda": 2.5,  # Conservative leverage
        "min_interest_coverage": 5.0,  # Real interest expense, not fabricated
        "min_current_ratio": 1.0,  # Relaxed for banks/insurers (0 accepted)
        # ── Valuation (sector-relative percentile rank) ───────────────────
        # max_sector_pe_percentile: 70 -> "not in top 30% richest in sector"
        # Implemented as min_valuation_score (M3 sector-relative 0-100):
        # low valuation score means rich; a score < ~70 passes if
        # the mapping is approximately linear. Keep both semantics documented.
        "min_valuation_score": 30,  # Not in bottom-30 of valuation rank
        "max_ev_ebit": 18,  # Cross-sector EV/EBIT cap
        "min_dcf_mos": 0.15,  # 15% below DCF base case
        "max_p_fcf": 30,  # FCF-based valuation cap
        # ── Growth (multi-period) ─────────────────────────────────────────
        "min_revenue_cagr_5y": 0.03,  # 3%/y minimum (GDP + inflation)
        "min_eps_cagr_5y": 0.05,  # 5% EPS growth
        "min_pos_revenue_years_5y": 4,  # 4 of 5 years growing = consistency
        "max_revenue_cagr_5y": 0.40,  # >40%/y = unsustainable
        # ── Capital Allocation ────────────────────────────────────────────
        "min_total_shareholder_yield": 0.02,  # Div + buyback + debt-reduction
        # ── Composite gate (horizon score) ───────────────────────────────
        "min_composite_score_lt": 70,  # On revised LT-weighted composite
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. LT_PEA_DEFENSIVE — PEA-strict, lower-vol tilt
# ──────────────────────────────────────────────────────────────────────────────

LT_PEA_DEFENSIVE: _PresetDict = {
    "horizon": "long_term",
    "name": "LT PEA Defensive",
    "description": (
        "PEA-only version of LT_QUALITY_COMPOUNDER with a lower-volatility tilt. "
        "Adds beta cap, minimum dividend yield, and payout sustainability filter. "
        "Raises market-cap floor to €1B for liquidity stability."
    ),
    "requires": [
        "GrossMargin_Stddev_5y",
        "RevenueCAGR_5y",
        "EPS_CAGR_5y",
        "PosRevenueYears_5y",
        "TotalShareholderYield",
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **_UNIVERSAL_PREFILTERS,
        "min_data_completeness": 0.80,
        # PEA-only: EU/EEA-domiciled companies
        "pea_only": True,
        # Raise market-cap floor for stability
        "min_market_cap": 1_000_000_000,  # €1B+
        # ── Quality / Profitability (same as LT_QUALITY_COMPOUNDER) ───────
        "min_roic": 0.12,
        "min_roic_5y_avg": 0.10,
        "min_gross_profitability": 0.20,
        "max_gross_margin_stddev_5y": 0.05,
        "min_fcf_margin": 0.05,
        "min_ccr_3y_avg": 0.70,
        "min_f_score": 7,
        # ── Financial Health ──────────────────────────────────────────────
        "min_altman_z": 2.6,
        "max_nd_ebitda": 2.5,
        "min_interest_coverage": 5.0,
        "min_current_ratio": 1.0,
        # ── Defensive overrides ───────────────────────────────────────────
        "max_beta": 1.0,  # Defensive bias — below-market vol
        "min_div_yield": 0.02,  # Income kicker (PEA tax efficiency)
        "max_payout_ratio": 0.65,  # Dividend sustainability
        # Exclude energy producers on ESG grounds (optional, surfaced in UI)
        "exclude_sectors": ["Tobacco", "Gambling", "Coal_Mining", "Energy_Producers"],
        # ── Valuation ─────────────────────────────────────────────────────
        "min_valuation_score": 30,
        "max_ev_ebit": 18,
        "min_dcf_mos": 0.15,
        "max_p_fcf": 30,
        # ── Growth ────────────────────────────────────────────────────────
        "min_revenue_cagr_5y": 0.03,
        "min_eps_cagr_5y": 0.05,
        "min_pos_revenue_years_5y": 4,
        "max_revenue_cagr_5y": 0.40,
        # ── Capital Allocation ────────────────────────────────────────────
        "min_total_shareholder_yield": 0.02,
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_lt": 70,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. LT_DEEP_VALUE — contrarian; anti-value-trap gates
# ──────────────────────────────────────────────────────────────────────────────

LT_DEEP_VALUE: _PresetDict = {
    "horizon": "long_term",
    "name": "LT Deep Value",
    "description": (
        "Contrarian approach: cheap on multiples but not garbage. "
        "Anti-value-trap gates include F-Score ≥ 6, Altman Z'' ≥ 1.8, "
        "ROIC 5y avg ≥ 6%, and positive FCF in ≥ 3 of last 5 years."
    ),
    "requires": [
        "PosRevenueYears_5y",  # positive_fcf_3of5_years
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **_UNIVERSAL_PREFILTERS,
        # ── Cheap on multiples (sector-relative bottom-30% cheapest) ───────
        # max_sector_pe_percentile: 30 -> bottom-30% richest = cheapest tier
        # Implemented as max_valuation_score: at most 30% of peers are cheaper.
        # Using min_valuation_score would be confusing here; use a dedicated key.
        "max_valuation_score": 30,  # In the cheapest 30% of sector peers
        "max_pb": 1.5,  # Book-value floor
        "max_ev_ebit": 9,  # Cross-sector cheap cap
        "min_dcf_mos": 0.30,  # 30%+ below DCF — larger MoS required
        # ── Anti-value-trap gates ─────────────────────────────────────────
        "min_f_score": 6,  # F-Score ≥ 6 filters fading businesses
        "min_altman_z": 1.8,  # Out of distress zone (above grey-zone floor)
        "min_roic_5y_avg": 0.06,  # Generates some returns on capital
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_lt": 60,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 4. MT_GARP — Growth At Reasonable Price
# ──────────────────────────────────────────────────────────────────────────────

MT_GARP: _PresetDict = {
    "horizon": "medium_term",
    "name": "MT GARP",
    "description": (
        "Quality is necessary but not sufficient: we need a re-rating catalyst. "
        "Forward valuation + earnings revisions + margin expansion + technical "
        "confirmation (price above 200dma, positive 3m relative strength)."
    ),
    "requires": [
        "Forward_PE",  # max_forward_pe
        "PEG_Forward",  # max_peg_forward
        "EV_EBIT_Forward",  # max_ev_ebit_forward
        "RevenueGrowth_Acceleration",  # min_revenue_growth_acceleration
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **_UNIVERSAL_PREFILTERS,
        # ── Forward valuation (not trailing) ─────────────────────────────
        "max_forward_pe": 18,  # Pay only fair price
        "max_peg_forward": 1.3,  # Growth-adjusted valuation cap
        "max_ev_ebit_forward": 14,  # Forward EV/EBIT if estimates available
        # ── Catalyst signals ──────────────────────────────────────────────
        "min_eps_revision_3m": 0.0,  # Not declining (EPS_Rev_90d column)
        "min_eps_revision_6m": 0.02,  # +2% upward revision in 6 months
        "min_operating_margin_trend_2y": 0.005,  # Op margin expanding 50bp/y
        "min_revenue_growth_yoy": 0.05,  # Currently growing
        "min_revenue_growth_acceleration": 0.0,  # Latest quarter ≥ trailing avg
        # ── Quality floor ─────────────────────────────────────────────────
        "min_roic": 0.10,
        "min_f_score": 6,
        "min_altman_z": 2.0,  # Grey-zone OK, distress excluded
        # ── Capital structure ─────────────────────────────────────────────
        "max_nd_ebitda": 3.0,
        # ── Technical confirmation ────────────────────────────────────────
        "price_above_200dma": True,  # Above_200DMA column (M9)
        "min_relative_strength_3m_vs_index": 0.0,  # RS_3m > 0
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_mt": 65,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 5. MT_TURNAROUND — operational improvement; higher risk
# ──────────────────────────────────────────────────────────────────────────────

MT_TURNAROUND: _PresetDict = {
    "horizon": "medium_term",
    "name": "MT Turnaround",
    "description": (
        "Speculative — size positions smaller (max 3% of portfolio). "
        "Target companies that were bad and are getting better: FCF turning positive, "
        "operating margin improving ≥ 300bp YoY, financially survivable (Altman ≥ 1.5)."
    ),
    "requires": [
        "OpMarginImprovement_YoY",  # min_op_margin_improvement_yoy
        "OpMargin_IsPositive",  # current_year_op_margin_positive
        "DebtMaturities_2y_Covered",  # debt_maturities_2y_covered
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **_UNIVERSAL_PREFILTERS,
        # ── Was bad, getting better ───────────────────────────────────────
        "min_op_margin_improvement_yoy": 0.03,  # +300bp YoY improvement
        "positive_fcf_latest_year": True,  # Cash-positive latest year
        # ── Financially survivable ────────────────────────────────────────
        "min_altman_z": 1.5,  # Out of distress zone
        "positive_cash_balance": True,  # Positive cash balance
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_mt": 55,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 6. MT_INCOME — yield + sustainability + growth
# ──────────────────────────────────────────────────────────────────────────────

MT_INCOME: _PresetDict = {
    "horizon": "medium_term",
    "name": "MT Income",
    "description": (
        "Dividend-focused medium-term strategy suited for PEA. "
        "Targets dividend growers (not yield traps): FCF coverage ≥ 1.4×, "
        "≥ 10 consecutive dividend years, payout ≤ 75%."
    ),
    "requires": [
        "DivGrowth_5y_CAGR",  # min_dividend_growth_5y_cagr
        "FCF_DivCoverage",  # min_fcf_dividend_coverage
        "ConsecutiveDivYears",  # min_consecutive_dividend_years
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **_UNIVERSAL_PREFILTERS,
        # ── Dividend quality ──────────────────────────────────────────────
        "min_div_yield": 0.035,  # 3.5% starting yield
        "max_payout_ratio": 0.75,  # Sustainability: ≤ 75% of earnings paid
        "min_dividend_growth_5y_cagr": 0.03,  # Dividend growers, not yield traps
        "min_fcf_dividend_coverage": 1.4,  # FCF / dividends paid > 1.4×
        "min_consecutive_dividend_years": 10,  # Track record
        # ── Financial health ──────────────────────────────────────────────
        "max_nd_ebitda": 3.5,
        "min_f_score": 6,
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_mt": 55,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 7. ST_MOMENTUM_QUALITY — academic momentum + quality floor
# ──────────────────────────────────────────────────────────────────────────────

ST_MOMENTUM_QUALITY: _PresetDict = {
    "horizon": "short_term",
    "name": "ST Momentum Quality",
    "description": (
        "Quantitative momentum + quality floor: 12-1 momentum, 3m relative strength, "
        "technical regime (golden cross), volume surge, earnings catalyst. "
        "Quality floor prevents chasing pump-and-dump names."
    ),
    # PEA warning: ST trading inside PEA risks closing the account on the 5y rule.
    "recommended_account": "CTO",
    "pea_warning": True,
    "requires": [
        "Momentum_12_1_Quartile",  # momentum_12_1: top_quartile check
        "Short_Interest_Trend",  # short_interest_trend
    ],
    "filters": {
        # ── Universal pre-filters (ST raises market-cap floor) ────────────
        **{**_UNIVERSAL_PREFILTERS, "min_market_cap": 500_000_000},
        "min_avg_daily_volume_eur": 2_000_000,  # Real liquidity for execution
        # ── Momentum signals (M9 columns) ─────────────────────────────────
        "price_above_50dma": True,  # Above_50DMA
        "price_above_200dma": True,  # Above_200DMA
        "ma_50_above_ma_200": True,  # Golden_Cross
        "min_volume_surge_5d_vs_90d": 1.3,  # Volume_Surge ≥ 1.3
        # ── Earnings catalyst ─────────────────────────────────────────────
        "min_sue_z_score": 1.0,  # Strong beat (SUE column from M9)
        "min_eps_revision_3m": 0.0,  # Not declining
        # ── Sentiment ─────────────────────────────────────────────────────
        "min_news_sentiment_30d": 0.0,  # Neutral or positive (NaN = pass)
        # ── Quality floor (avoid pump-and-dump) ───────────────────────────
        "min_altman_z": 1.5,
        "min_f_score": 5,  # Lower than LT but not junk
        # ── Risk gates ────────────────────────────────────────────────────
        "max_beta": 1.8,
        "max_realized_vol_1y": 0.50,  # 50% annualized — no 100% vol names
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_st": 50,  # Lower bar — momentum is the signal
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 8. ST_EARNINGS_DRIFT — post-earnings announcement drift (PEAD)
# ──────────────────────────────────────────────────────────────────────────────

ST_EARNINGS_DRIFT: _PresetDict = {
    "horizon": "short_term",
    "name": "ST Earnings Drift",
    "description": (
        "Pure event-driven PEAD trade: strong earnings beat (SUE ≥ 1.5), "
        "confirmed by volume surge and gap-up, held 30–60 days post-announcement. "
        "Exit on 50dma break, negative relative strength, or negative news."
    ),
    "recommended_account": "CTO",
    "pea_warning": True,
    "requires": [
        "EarningsAnnouncement_Within5d",  # trigger: earnings_announcement_within_5d
        "GapUp_Pct",  # gap_up_pct ≥ 3%
        "NoNegativeGuidanceRevision",  # no_negative_guidance_revision
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **{**_UNIVERSAL_PREFILTERS, "min_market_cap": 500_000_000},
        # ── Beat quality ──────────────────────────────────────────────────
        "min_sue_z_score": 1.5,  # Strong beat (SUE column from M9)
        "min_volume_surge_5d_vs_90d": 2.0,  # 2× volume surge on announcement day
        # ── Momentum confirmation ─────────────────────────────────────────
        "min_eps_revision_3m": 0.0,  # Positive revision post-announcement
        # ── No negative guidance ──────────────────────────────────────────
        "min_news_sentiment_30d": 0.0,  # Neutral or positive
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_st": 45,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 9. ST_OVERSOLD_BOUNCE — mean-reversion; smaller positions
# ──────────────────────────────────────────────────────────────────────────────

ST_OVERSOLD_BOUNCE: _PresetDict = {
    "horizon": "short_term",
    "name": "ST Oversold Bounce",
    "description": (
        "Mean-reversion trade using Connors RSI(2) extreme oversold (< 10) "
        "combined with long-term uptrend confirmation (price above 200dma). "
        "Hold 3–10 days targeting the 50dma; stop-loss = 1 ATR below entry."
    ),
    "recommended_account": "CTO",
    "pea_warning": True,
    # RSI_2 requires intraday or high-frequency price data; not yet plumbed.
    # price_above_200dma is already a column from M9 momentum module.
    "requires": [
        "RSI_2",  # rsi_2_below_10: extreme oversold trigger
        "NoEarningsWithin3d",  # no_earnings_within_3d guard
        "NoRecentNegativeNews",  # no_recent_negative_news guard
    ],
    "filters": {
        # ── Universal pre-filters ─────────────────────────────────────────
        **{**_UNIVERSAL_PREFILTERS, "min_market_cap": 500_000_000},
        # ── Mean-reversion setup ──────────────────────────────────────────
        # RSI_2 < 10 is the primary entry trigger; column not yet available.
        # When RSI_2 is plumbed, add: "max_rsi_2": 10
        "price_above_200dma": True,  # Only in long-term uptrends
        # ── Sentiment safety guard ────────────────────────────────────────
        "min_news_sentiment_30d": 0.0,  # No recent negative news catalyst
        # ── Risk gates ────────────────────────────────────────────────────
        "min_altman_z": 1.5,
        # ── Composite gate ────────────────────────────────────────────────
        "min_composite_score_st": 40,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────

PRESET_REGISTRY: dict[str, _PresetDict] = {
    "LT_QUALITY_COMPOUNDER": LT_QUALITY_COMPOUNDER,
    "LT_PEA_DEFENSIVE": LT_PEA_DEFENSIVE,
    "LT_DEEP_VALUE": LT_DEEP_VALUE,
    "MT_GARP": MT_GARP,
    "MT_TURNAROUND": MT_TURNAROUND,
    "MT_INCOME": MT_INCOME,
    "ST_MOMENTUM_QUALITY": ST_MOMENTUM_QUALITY,
    "ST_EARNINGS_DRIFT": ST_EARNINGS_DRIFT,
    "ST_OVERSOLD_BOUNCE": ST_OVERSOLD_BOUNCE,
}


def get_preset(name: str) -> _PresetDict:
    """Return the named preset dict.

    Raises
    ------
    KeyError
        When ``name`` is not found in ``PRESET_REGISTRY``.  Error message
        includes the list of valid names so the caller can surface a helpful
        diagnostic.
    """
    if name not in PRESET_REGISTRY:
        valid = sorted(PRESET_REGISTRY.keys())
        raise KeyError(f"Unknown preset {name!r}. Valid names: {valid}")
    return PRESET_REGISTRY[name]


def list_presets() -> list[dict[str, str]]:
    """Return a summary list of all registered presets.

    Each entry contains ``name``, ``horizon``, and ``description``.

    Returns
    -------
    list[dict]
        Sorted by horizon (long_term, medium_term, short_term) then
        alphabetically within each horizon.
    """
    order = {"long_term": 0, "medium_term": 1, "short_term": 2}
    entries = [
        {
            "name": k,
            "horizon": v["horizon"],
            "description": v.get("description", ""),
            "recommended_account": v.get("recommended_account", ""),
            "pea_warning": v.get("pea_warning", False),
        }
        for k, v in PRESET_REGISTRY.items()
    ]
    entries.sort(key=lambda e: (order.get(e["horizon"], 99), e["name"]))
    return entries


# ──────────────────────────────────────────────────────────────────────────────
# screen_horizon_preset — convenience wrapper
# ──────────────────────────────────────────────────────────────────────────────


def screen_horizon_preset(df: pd.DataFrame, preset_name: str) -> pd.DataFrame:
    """Apply a named horizon preset's filters and sort by the relevant horizon score.

    Applies the preset's ``filters`` dict via :func:`screener.apply_filters`,
    then requires that ``passes_gates_<horizon>`` is True (LT/MT/ST gates from
    M7), and finally sorts descending by ``score_lt`` / ``score_mt`` / ``score_st``
    as appropriate.

    The ``passes_gates_*`` gate columns are produced by
    :func:`src.analysis.horizon_scoring.score_three_horizons`  (M7).  When
    they are absent (e.g. DataFrame has not yet been run through the scoring
    engine), the gate filter is skipped — older DataFrames still get the
    filter-only narrowing.

    Parameters
    ----------
    df : pd.DataFrame
        Universe already enriched by ``score_dataframe`` (M3/M5/M9 sub-scores,
        M7 horizon columns, M6 DCF columns all optional but preferred).
    preset_name : str
        One of the keys in ``PRESET_REGISTRY``.

    Returns
    -------
    pd.DataFrame
        Filtered and sorted subset; may be empty when the preset is very
        strict or the universe is small / data-sparse.
    """
    from src.strategy.screener import apply_filters  # avoid circular import at module level

    preset = get_preset(preset_name)
    horizon = preset["horizon"]  # "long_term" | "medium_term" | "short_term"

    score_col_map = {
        "long_term": "score_lt",
        "medium_term": "score_mt",
        "short_term": "score_st",
    }
    gates_col_map = {
        "long_term": "passes_gates_lt",
        "medium_term": "passes_gates_mt",
        "short_term": "passes_gates_st",
    }

    score_col = score_col_map[horizon]
    gates_col = gates_col_map[horizon]

    # Build the filter spec: use preset filters; pea_only derived from preset
    pea_only = bool(preset["filters"].get("pea_only", False))
    filtered = apply_filters(df, preset["filters"], pea_only=pea_only)

    # Apply the M7 investability gate when available on the DataFrame.
    # NaN means the gate could not be evaluated (missing input data) — treat
    # it as "not blocking" rather than as a hard fail, so universes that
    # lack technical columns (DMAs, momentum) still surface results from
    # the fundamentals-driven gates.
    if gates_col in filtered.columns:
        filtered = filtered[filtered[gates_col].fillna(True).astype(bool)]

    # Sort by the horizon score; fall back to Composite_Score for legacy DFs
    if score_col in filtered.columns:
        return filtered.sort_values(score_col, ascending=False)
    elif "Composite_Score" in filtered.columns:
        return filtered.sort_values("Composite_Score", ascending=False)
    return filtered
