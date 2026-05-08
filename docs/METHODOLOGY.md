# Methodology v2 — Three-Horizon Quantitative Valuation

**Status:** Active (replaces v1).
**Last updated:** 2026-05-08.
**Companion docs:** [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) (architecture), [`DATA_SOURCES.md`](DATA_SOURCES.md) (data layer), [`adr/`](adr/) (decision records), [`backtests/methodology.md`](backtests/methodology.md) (backtest framework).

---

## 0. Why v2 exists

The v1 engine produced one composite score and one Buy/Sell signal per ticker, conflating long-term compounders with short-term momentum trades. The 2026-05-08 audit (`AUDIT_2026-05-08_Screener_Metrics.md` in the project's research vault) catalogued ten fundamental defects in v1 — fabricated EBIT, fabricated interest expense, broken Piotroski, fictitious Altman inputs, a misnamed `_percentile_score`, no DCF, and so on. Milestones M0–M12 rebuilt the engine end-to-end. v2 is the result.

The two structural changes:

1. **Three horizons replace one.** Long-Term (5y+), Medium-Term (1–3y), Short-Term (<6mo) each receive their own composite, signal, and gate set. See [ADR-0001](adr/0001-three-horizon-scoring.md).
2. **Sector-relative percentiles replace hardcoded linear maps.** A SaaS at P/E 35 is no longer punished for being a SaaS; it's compared to its sector peers. See [ADR-0003](adr/0003-sector-relative-percentile.md).

---

## 1. Overview — three horizons, one ticker

For every ticker the engine emits three independent composites plus a quality/risk/momentum block:

```
score_lt, signal_lt, passes_gates_lt, blockers_lt   (long-term, 5y+)
score_mt, signal_mt, passes_gates_mt, blockers_mt   (medium-term, 1–3y)
score_st, signal_st, passes_gates_st, blockers_st   (short-term, <6mo)
```

Each horizon runs the same machinery, parameterised by:

- a **weight vector** over 8 sub-score categories (different per horizon)
- a **gate set** (different per horizon — ST is stricter on liquidity, LT on data completeness)
- a shared **DCF margin-of-safety** input that lets the M6 two-criterion signal kick in

### Signal flowchart (per horizon)

```
  raw fundamentals + price history
              |
              v
  ┌──────────────────────────────────────┐
  │ M3 sub-score columns (sector-rel)    │  Valuation_Score, Profitability_Score,
  │                                      │  Health_Score, Growth_Score,
  │                                      │  Shareholder_Score, Risk_Score
  └──────────────┬───────────────────────┘
                 |
                 +-- M5 columns: EarningsQuality_Score, Moat_Score, Risk_Score_v2
                 +-- M6 columns: DCF_FairValue_{Low,Mid,High}, DCF_MoS_{Low,Mid,High}, WACC_Used
                 +-- M9 columns: Momentum_Score, Above_50DMA, Above_200DMA, Volume_Surge,
                 |                EPS_Rev_30d, EPS_Rev_90d, SUE, Sentiment_30d, Sentiment_Trend
                 v
        ┌────────────────────────┐
        │ M7 horizon scoring     │  weighted mean over present categories,
        │ (renormalised over     │  renormalised when sub-scores missing
        │  present columns)      │
        └────────┬───────────────┘
                 |
        ┌────────v───────────────┐
        │ M7 gate evaluation     │  data_completeness, distress (Altman Z),
        │                        │  market_cap, years_listed, vol, momentum
        └────────┬───────────────┘
                 |
        ┌────────v───────────────┐
        │ generate_signal()      │  composite >=80 AND MoS>=0.30 -> Strong Buy
        │                        │  composite >=65 AND MoS>=0.15 -> Buy
        │                        │  MoS <= -0.30 -> Strong Sell
        │                        │  composite <=40 OR MoS <= -0.15 -> Sell
        │                        │  else Hold
        └────────────────────────┘
```

Pure functions throughout. No I/O inside scoring; the data layer (`backend/app/services/market_data/`) hands a single DataFrame to `score_universe`, which delegates to the modules below.

---

## 2. Sub-score categories (M3 + M5 + M9)

Eight categories feed the horizon composites. Each emits a 0–100 column. Missing inputs propagate as NaN, and the M7 weighted mean drops NaN sub-scores out of the calculation rather than substituting a neutral 50 (`src/analysis/horizon_scoring.py`, `_renormalised_weighted_mean`).

| Category | Source module | Input columns | Output column | Sector-relative? |
|---|---|---|---|---|
| Valuation | `src/analysis/scoring_engine.py` (`valuation_score_df`) | PE, PB, PS, PFCF, EV_EBITDA, EV_Sales | `Valuation_Score` | yes — M3 |
| Profitability | `src/analysis/scoring_engine.py` (`profitability_score_df`) | ROE, ROA, ROIC, NetMargin, OperatingMargin | `Profitability_Score` | yes — M3 |
| Health | `src/analysis/scoring_engine.py` (`health_score_df`) | CurrentRatio, DebtEquity, InterestCoverage, Altman Z | `Health_Score` | partial — M3 |
| Growth | `src/analysis/scoring_engine.py` (`growth_score_df`) | RevenueGrowth (M3 still TTM only; multi-period CAGRs queued for M14) | `Growth_Score` | yes — M3 |
| Shareholder / Capital Allocation | `src/analysis/scoring_engine.py` (`shareholder_score_df`) | DivYield, PayoutRatio, BuybackYield (when present) | `Shareholder_Score` | yes — M3 |
| Risk (legacy) | `src/analysis/scoring_engine.py` (`risk_score_df`) | Beta, InterestCoverage | `Risk_Score` | partial |
| **Risk v2** | `src/analysis/risk_metrics.py` (`risk_score_real`) | Realized_Vol_1y, MaxDrawdown_3y, NetDebt_EBITDA, real InterestCoverage, Altman Z, Beta | `Risk_Score_v2` | yes — M5 |
| **Earnings Quality** | `src/analysis/earnings_quality.py` (`earnings_quality_score`) | M-Score, Sloan accruals, CCR_5y | `EarningsQuality_Score` | yes — M5 |
| **Moat** | `src/analysis/quality_moat.py` (`moat_score`) | GP/TA, ROIC 5y avg + stddev, OpMargin stability, ROIC – WACC, reinvestment efficiency | `Moat_Score` | yes — M5 |
| **Momentum** | `src/analysis/momentum.py` (`momentum_score`) | Momentum_12_1, RS_3m, Above_50DMA, Above_200DMA, Volume_Surge | `Momentum_Score` | partial |

**M3 ranking note.** Sector-relative scoring lives in `src/analysis/sector_percentile.py` (`score_sector_relative`). For each sector with `>= 5` non-NaN peers it returns `df.groupby(Sector)[metric].rank(pct=True) * 100`. Sectors below the peer floor fall back to the global rank. NaN inputs preserve NaN — no imputation.

The legacy `Risk_Score` and the M5 `Risk_Score_v2` both exist in the DataFrame; M7 reads `Risk_Score_v2` because it incorporates real volatility and drawdown rather than just Beta. The legacy column stays alive for snapshot-test backwards compatibility until M14.

---

## 3. Quality signals (M4 + M5)

Four academically-grounded signals replace the v1 stand-ins.

### 3.1 Real Piotroski F-Score

`src/analysis/quality_signals.py` (`piotroski_f_score`). Nine signals, each `+1` if satisfied, `0` if violated, `None` if the inputs are missing. The aggregator sums the non-None signals — a company with only 6 of 9 signals available scores 0–6, not 0–9 (matches Piotroski 2000's data-completeness handling).

| # | Signal | Test |
|---|---|---|
| 1 | ROA positive | `ROA > 0` |
| 2 | CFO positive | `OperatingCashflow > 0` |
| 3 | ΔROA improving | `ROA > ROA_PriorYear` (real YoY, not "ROA > 5%" proxy) |
| 4 | Accruals quality | `OperatingCashflow > NetIncome` (NaN-safe; defaults reversed from v1 bug) |
| 5 | ΔLeverage decreasing | `LongTermDebt/TA < LongTermDebt_PriorYear/TA_PriorYear` |
| 6 | ΔLiquidity improving | `CurrentRatio > CurrentRatio_PriorYear` |
| 7 | No dilution | `Shares <= Shares_PriorYear * 1.005` (real share count from `tk.get_shares_full()`; v1 awarded this point unconditionally) |
| 8 | ΔGross margin improving | `GrossMargin > GrossMargin_PriorYear` |
| 9 | ΔAsset turnover improving | `Revenue/TA > Revenue_PriorYear/TA_PriorYear` |

### 3.2 Altman Z'' (non-manufacturers) and Z classic (manufacturers)

`src/analysis/quality_signals.py` (`altman_z_select`). Sector-aware dispatch:

- **Manufacturers** (`Industrials`, `Materials`, `Energy`, `Consumer Cyclical`, `Consumer Defensive`) use the classic 5-factor Z: `1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5`.
- **Everyone else** uses Z'': `6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4` (no asset-turnover X5).

X1 uses **real** working capital (`CurrentAssets − CurrentLiabilities`), not v1's `Cash − 0.3 × TotalDebt` proxy. X2 uses **real** retained earnings, not v1's `0.4 × Equity` proxy. X3 uses **real** EBIT, not v1's EBIT-aliased-to-EBITDA bug. See [ADR-0004](adr/0004-no-fabricated-values.md).

Zones: Z'' > 2.6 = Safe, 1.1 < Z'' < 2.6 = Grey, Z'' < 1.1 = Distress.

### 3.3 Beneish M-Score

`src/analysis/earnings_quality.py` (`beneish_m_score`). Eight-variable manipulation flag from Beneish (1999):

```
M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
    + 0.115*DEPI − 0.172*SGAI + 4.679*TATA − 0.327*LVGI
```

Threshold: `M > -1.78` flags potential earnings manipulation. Carried as a flag, not an auto-screen-out — manipulator-flagging models have false positives. Required inputs include current AND prior-year Receivables, Sales, GrossMargin, TotalAssets, CurrentAssets, PPE, D&A, SG&A, NetIncome, CFO, LongTermDebt, CurrentLiabilities. Any missing → returns NaN.

### 3.4 Sloan accruals and CCR

- **Sloan accruals**: `(NetIncome − CFO) / Avg(TotalAssets)`. > 0.10 = aggressive; > 0.20 = very aggressive. < -0.10 = conservative (positive signal).
- **Cash Conversion Ratio 5y avg**: `mean(FCF_year / NI_year)` over the last 5 years where NI > 0. > 1.0 = excellent; 0.7–1.0 = healthy; < 0.7 = quality concern.

The combined `EarningsQuality_Score` blends these three (M-Score, Sloan, CCR) into a sector-relative composite via `earnings_quality_score(df)`.

---

## 4. DCF — two-stage with sensitivity grid (M6)

`src/analysis/dcf.py` (`dcf_with_sensitivity`).

### Mechanics

1. **WACC** via CAPM cost of equity + after-tax cost of debt:
   `WACC = (E/V)*Re + (D/V)*Rd*(1-Tc)` with `Re = Rf + β*ERP`.
   Defaults from `settings.yaml` `valuation.dcf`: Rf = 3% (10Y OAT), ERP = 5.5% (Damodaran), Tc = 25% (FR corporate), Rd = 5% pre-tax.
2. **Revenue glide**: linear fade from current YoY growth to terminal growth over 5 years (`build_revenue_glide`). Avoids Damodaran's "fat tail" problem for fast growers.
3. **5-year explicit FCF projection**: `FCF_t = Revenue_t * FCF_margin`. FCF_margin defaults to TTM, derivable from FCF + Revenue when `FCFMargin` column is missing.
4. **Terminal value** via Gordon growth: `TV = FCF_5 * (1 + g) / (WACC − g)`. Returns NaN when `WACC <= g`; warns "WACC <= TGR ... terminal model invalid".
5. **Equity value** = sum of discounted FCFs + discounted TV − net debt.
6. **Per-share** = equity value / shares outstanding. Negative values are NOT clipped — distressed firms can produce negative intrinsic and that should propagate.

### Sensitivity grid

A 3×3 grid runs WACC ± 1pp and TGR ± 50bp, producing 9 scenarios:

```
       tgr-       tgr        tgr+
wacc-  scenario  scenario   scenario
wacc   scenario  *base*     scenario
wacc+  scenario  scenario   scenario
```

Output columns: `intrinsic_low` (min over grid), `intrinsic_mid` (centre cell), `intrinsic_high` (max), and the corresponding margins of safety `mos_low`, `mos_mid`, `mos_high`. The `pv_terminal_pct` ratio (terminal value / enterprise value) is exposed; > 75% triggers a warning that the valuation is dominated by the terminal assumption.

### Margin of safety convention

```
mos = (intrinsic - price) / price
> 0  ⇒  undervalued (e.g. 0.30 = price is 70% of intrinsic)
< 0  ⇒  overvalued  (e.g. -0.30 = price is 130% of intrinsic)
```

### Strong Buy gate

The `generate_signal` function in `src/analysis/scoring_engine.py` activates the M6 two-criterion path when MoS is finite:

```
Strong Buy : composite >= 80 AND mos >= 0.30   (price < 70% intrinsic)
Buy        : composite >= 65 AND mos >= 0.15   (price < 85% intrinsic)
Strong Sell: mos <= -0.30                      (price > 130% intrinsic)
Sell       : composite <= 40   OR  mos <= -0.15
Hold       : otherwise
```

When the DCF returns NaN (e.g. for financials whose FCF margin is undefined, or when shares/revenue/beta are missing), the rule degrades gracefully to legacy composite-only thresholds. The DCF block on the company response always returns the warnings list — callers know why the value is missing.

---

## 5. Per-horizon weights and gates

The `horizons:` block in `settings.yaml` is the source of truth. Each horizon defines a weights map and a gates map, and `src/analysis/horizon_scoring.py` consumes them directly without backend translation.

### Weights (sum to 1.00 per horizon)

| Category | LT | MT | ST |
|---|---|---|---|
| `valuation` | 0.20 | 0.20 | 0.05 |
| `profitability` | 0.25 | 0.15 | 0.05 |
| `health` | 0.15 | 0.15 | 0.10 |
| `earnings_quality` | 0.10 | 0.10 | 0.05 |
| `growth` | 0.10 | 0.15 | 0.05 |
| `capital_allocation` | 0.10 | 0.05 | 0.05 |
| `risk` | 0.10 | 0.10 | 0.10 |
| `momentum` | 0.00 | 0.10 | 0.55 |

Rationale: LT favours quality + earnings integrity; MT adds catalyst (momentum + growth); ST is dominated by momentum because price/volume/sentiment are the dominant signals on sub-6-month horizons.

### Gates per horizon

| Gate | LT | MT | ST | Source column |
|---|---|---|---|---|
| `min_data_completeness` | 0.70 | 0.60 | 0.50 | `data_completeness` |
| `max_distress` (Altman Z floor) | 1.1 | 1.1 | 1.5 | `Altman_Z` |
| `min_market_cap` (EUR) | 100M | 100M | 500M | `MarketCap` |
| `min_years_listed` | 3 | — | — | `YearsListed` |
| `min_avg_volume` | — | — | 2M | `AvgVolume` |
| `max_realized_vol_1y` | — | — | 0.5 | `Realized_Vol_1y` |
| `pea_warning` / `recommended_account: CTO` | — | — | yes | metadata |

ST also blocks on `missing_momentum` — when `Momentum_Score` is NaN the ST composite is mostly noise, so the gate fails rather than reporting a misleading score.

When a gate's input is NaN, the gate fails with `missing_<key>` rather than silently passing. Gating must be conservative.

### Composite computation

```python
# src/analysis/horizon_scoring.py
def _renormalised_weighted_mean(row, weights, sub_score_columns) -> float:
    present_score, present_weight = 0.0, 0.0
    for cat, w in weights.items():
        col = sub_score_columns.get(cat)
        val = row.get(col, np.nan)
        if not _is_finite(val):
            continue
        present_score += float(val) * float(w)
        present_weight += float(w)
    return present_score / present_weight if present_weight > 0 else float("nan")
```

A name with only 5 of 8 sub-scores still scores correctly — the present categories are renormalised over the present weights. A name where every sub-score is NaN scores NaN (which then signals as "Hold" via the legacy 50.0 fallback rather than crashing).

---

## 6. Universal pre-filters (screener)

All 9 horizon presets in `src/strategy/horizon_presets.py` extend a shared `_UNIVERSAL_PREFILTERS` block:

| Filter | Threshold | Reason |
|---|---|---|
| `min_market_cap` | €100M (ST: €500M) | Liquidity floor; reduces manipulation noise |
| `min_avg_daily_volume_eur` | €500K (ST: €2M) | Real liquidity (volume × price) |
| `min_years_listed` | 3 | Excludes IPO honeymoon, ensures multi-year metrics exist |
| `exclude_sectors` | Tobacco, Gambling, Coal_Mining (LT_PEA_DEFENSIVE adds Energy_Producers) | settings.yaml ESG list — finally wired (audit §2.7) |
| `not_in_distress` | Altman Z >= 1.1 | Same threshold as horizon distress gate |
| `min_data_completeness` | 0.70 (LT presets raise to 0.80) | Skip names where >30% of inputs are NaN |

Settings.yaml `screener:` previously declared `exclude_sectors`, `min_avg_volume`, `min_years_listed` but never wired them — fixed in M1.

---

## 7. Horizon presets (M8)

Nine presets, each a self-contained filter dict consumed by `apply_filters` and sorted by the matching horizon score via `screen_horizon_preset(df, "PRESET_NAME")`.

### Long-Term (5y+)

- **`LT_QUALITY_COMPOUNDER`** — Default LT. ROIC ≥ 12%, Piotroski ≥ 7, Altman Z'' ≥ 2.6, ND/EBITDA ≤ 2.5, sector-relative valuation cap, DCF MoS ≥ 15%, multi-period revenue/EPS CAGRs.
- **`LT_PEA_DEFENSIVE`** — PEA-strict, lower-vol tilt. Beta ≤ 1.0, Div Yield ≥ 2%, payout ≤ 65%, market cap ≥ €1B, ESG sector exclusions (incl. Energy_Producers).
- **`LT_DEEP_VALUE`** — Contrarian. P/B ≤ 1.5, EV/EBIT ≤ 9, DCF MoS ≥ 30%. Anti-value-trap gates: Piotroski ≥ 6, Altman Z ≥ 1.8, ROIC 5y avg ≥ 6%.

### Medium-Term (1–3y)

- **`MT_GARP`** — Growth at reasonable price. Forward P/E ≤ 18, PEG ≤ 1.3, EPS revisions positive 6m, op margin trend +50bp/y, price > 200dma, 3m relative strength positive.
- **`MT_TURNAROUND`** — Higher-risk operational improvement. Op margin improvement ≥ 300bp YoY, FCF positive latest year, Altman Z ≥ 1.5. Recommended position size ≤ 3%.
- **`MT_INCOME`** — Dividend-focused. Yield ≥ 3.5%, payout ≤ 75%, 5y dividend growth ≥ 3%, FCF coverage ≥ 1.4×, ≥ 10 consecutive dividend years.

### Short-Term (<6mo)

All ST presets carry `recommended_account: "CTO"` and `pea_warning: True`. See [§9 PEA caveat](#9-pea-caveat-for-short-term).

- **`ST_MOMENTUM_QUALITY`** — Quantitative momentum + quality floor. 12-1 momentum top quartile, golden cross, volume surge ≥ 1.3, SUE ≥ 1, Altman Z ≥ 1.5, Piotroski ≥ 5, max realised vol 50%.
- **`ST_EARNINGS_DRIFT`** — Post-Earnings Announcement Drift. Trigger: earnings within 5 days, SUE ≥ 1.5, volume surge ≥ 2.0, gap up ≥ 3%. Hold 30–60 days.
- **`ST_OVERSOLD_BOUNCE`** — Mean reversion. RSI(2) < 10, price > 200dma, hold 3–10 days, target 50dma, stop loss 1 ATR.

Sample backtest output: `docs/backtests/LT_QUALITY_COMPOUNDER_2022-01-01_to_2024-12-31.md`, `docs/backtests/MT_TURNAROUND_2022-01-01_to_2024-12-31.md`.

Presets reference columns that are only partially populated by the M2 hybrid fetcher (e.g. `Forward_PE`, `EV_EBIT_Forward`, `RSI_2`, `EarningsAnnouncement_Within5d`). Each preset declares missing columns in a `requires` list; `apply_filters` silently skips any filter key whose target column is absent — "skipped, not errored" semantics so adding a column incrementally never breaks existing runs.

---

## 8. Output schema — CompanyDetail JSON

The backend's `/api/company/{ticker}` returns a `CompanyDetail` (Pydantic) containing every block above. Example (truncated, NaN→null):

```json
{
  "ticker": "ASML.AS",
  "name": "ASML Holding NV",
  "sector": "Technology",
  "industry": "Semiconductor Equipment & Materials",
  "country": "NL",
  "exchange": "AMS",
  "pea_eligible": true,
  "pea_pme_eligible": false,
  "price": 690.40,
  "market_cap": 271000000000,

  "horizons": {
    "long_term":   {"score": 78.4, "signal": "Buy",      "passes_gates": true,  "blockers": [], "recommended_account": null},
    "medium_term": {"score": 71.2, "signal": "Buy",      "passes_gates": true,  "blockers": [], "recommended_account": null},
    "short_term":  {"score": 42.1, "signal": "Hold",     "passes_gates": false, "blockers": ["max_realized_vol_1y", "missing_momentum"], "recommended_account": "CTO"}
  },

  "sub_scores": {
    "valuation": 35.0,
    "health": 82.0,
    "profitability": 91.0,
    "growth": 73.0,
    "shareholder": 56.0,
    "risk_legacy": 64.0
  },

  "valuation": {
    "fair_value_low":  612.50,
    "fair_value_mid":  745.20,
    "fair_value_high": 882.10,
    "mos_low":  -0.113,
    "mos_mid":   0.079,
    "mos_high":  0.278,
    "wacc_used": 0.084,
    "warnings": []
  },

  "quality": {
    "piotroski_f": 8,
    "altman_z": 4.21,
    "altman_zone": "Safe",
    "graham_number": 312.40,
    "graham_mos": -54.7,
    "earnings_quality_score": 78.0,
    "moat_score": 88.0,
    "m_score": -2.41,
    "sloan_accruals": -0.024,
    "cash_conversion_ratio_5y": 1.05
  },

  "risk": {
    "risk_score": 71.0,
    "realized_vol_1y": 0.32,
    "max_drawdown_3y": -0.43,
    "net_debt_ebitda": -0.18,
    "interest_coverage": 38.4,
    "beta": 1.12
  },

  "momentum": {
    "momentum_12_1": -0.04,
    "rs_3m": -0.07,
    "above_50dma": false,
    "above_200dma": true,
    "golden_cross": true,
    "volume_surge": 0.94,
    "eps_revision_30d": 0.012,
    "eps_revision_90d": 0.034,
    "sue_z_score": 1.42,
    "sentiment_30d": 0.18,
    "sentiment_trend": -0.04
  },

  "metrics": {
    "pe": 38.4, "forward_pe": 28.1, "pb": 22.5, "ps": 9.8, "pfcf": 35.6,
    "ev_ebitda": 28.5, "ev_sales": 9.6, "peg": 1.8,
    "gross_margin": 0.515, "operating_margin": 0.318, "net_margin": 0.262, "fcf_margin": 0.275,
    "roe": 0.585, "roa": 0.162, "roic": 0.412,
    "revenue_growth": -0.12,
    "current_ratio": 1.42, "debt_equity": 0.31, "interest_coverage": 38.4,
    "div_yield": 0.0096, "payout_ratio": 0.32,
    "beta": 1.12
  },

  "data_completeness": 0.94,
  "data_source": "fmp+yfinance",
  "last_updated": "2026-05-08T07:00:00Z"
}
```

Schema models live in `backend/app/models/company.py`, `backend/app/models/horizons.py`. The full OpenAPI spec is at `openapi_v2.json` in the repo root.

---

## 9. PEA caveat for short-term

Short-term momentum trading inside a Plan d'Épargne en Actions is sub-optimal:

1. Frequent trading can trigger PEA's "broker frequent-trading" rule and forfeit the tax wrapper.
2. Withdrawals before the 5-year mark close the account and trigger PFU (30%).
3. PEA has no shorts and no leverage — half the alpha-extraction tools for ST are unavailable.

The engine surfaces this with `recommended_account: "CTO"` on ST passes (`src/analysis/horizon_scoring.py`, `score_three_horizons` final block) and the frontend renders a `<CTOWarningBanner>` whenever a PEA-eligible ticker shows a passing ST signal.

---

## 10. Settings reference

Quick map of `settings.yaml` knobs that affect scoring:

| Block | Key | Effect |
|---|---|---|
| `valuation.dcf` | `terminal_growth_rate`, `risk_free_rate`, `equity_risk_premium`, `tax_rate_default` | DCF defaults |
| `scoring` | `valuation_weight`, `financial_health_weight`, `profitability_weight`, `growth_weight`, `shareholder_return_weight`, `risk_weight` | Legacy single composite (kept alive for backwards-compat tests) |
| `signals` | `strong_buy.min_score`, `strong_buy.max_price_to_intrinsic`, ... | Signal threshold table; M6 made `max_price_to_intrinsic` actually bite |
| `horizons.long_term.weights` | `valuation`, `profitability`, ..., `momentum` | LT category weights |
| `horizons.long_term.gates` | `min_data_completeness`, `max_distress`, `min_market_cap`, `min_years_listed` | LT gates |
| `horizons.medium_term.weights` / `.gates` | (analogous) | MT |
| `horizons.short_term.weights` / `.gates` | adds `min_avg_volume`, `max_realized_vol_1y`, `pea_warning`, `recommended_account` | ST |
| `screener` | `min_market_cap`, `min_avg_volume`, `min_years_listed`, `exclude_sectors` | Universal pre-filters |
| `pea` | `eligible_countries`, `pea_pme_max_deposit` | PEA eligibility check (country-based) |
| `fmp` | `enabled`, `daily_limit` | Data layer kill-switch + quota cap |

---

## 11. Limitations and known gaps

Honest inventory, not a roadmap:

1. **Multi-period growth** — `growth_score_df` still uses TTM `RevenueGrowth` only; 5y CAGR over EPS / FCF / Revenue is queued for M14 (audit §2.1).
2. **Forward valuation** — `Forward_PE`, `EV_EBIT_Forward`, `Forward_PEG` are referenced by MT_GARP but not yet plumbed through `HybridDataFetcher`; `apply_filters` silently skips them.
3. **Backtest look-ahead bias** — M12's walk-forward backtest uses current-snapshot fundamentals as a proxy for historical inputs. Inflates apparent alpha for winners. Mitigation roadmap in `docs/backtests/methodology.md` §"Look-ahead bias".
4. **Survivorship bias** — Backtest universe is fixed at construction; delisted/acquired names silently absent from earlier rebalances.
5. **FMP free-tier coverage gaps** — Euronext (.PA, .AS) tickers often 404 on FMP statements; yfinance fallback covers most but not all. See [`backend/app/services/market_data/coverage_matrix.md`](../backend/app/services/market_data/coverage_matrix.md).
6. **Beneish M-Score requires both periods** — When prior-year inputs are missing (common for sub-3y listings), the M-Score is NaN and excluded from `EarningsQuality_Score`.
7. **DCF for financials** — Banks/insurers don't have a meaningful FCF margin; the DCF returns NaN with the warning "Non-positive FCF margin" or "FCF margin not derivable". Use Graham Number + sector-relative P/B for these instead.
8. **Sector taxonomy drift** — FMP uses GICS, yfinance uses Yahoo's taxonomy; sector-relative scoring may drift on tickers where the two disagree. Canonicalisation tracked as a known risk.
9. **WACC is per-ticker, not per-jurisdiction** — Tax rate defaults to 25% (FR); Irish-domiciled (12.5%) or German (29.9%) names use the same assumption. Tracked for M14.

---

## 12. References

- Audit (research vault, not in repo): `AUDIT_2026-05-08_Screener_Metrics.md` — the diagnosis that drove v2.
- ADRs: [`docs/adr/`](adr/) — five decision records for the structural choices (three horizons, hybrid data, sector-relative scoring, no fabrication, atomic schema replacement).
- Backtest framework: [`docs/backtests/methodology.md`](backtests/methodology.md).
- CHANGELOG: [`CHANGELOG.md`](../CHANGELOG.md) — milestone-by-milestone (M0–M12).
- OpenAPI: [`openapi_v2.json`](../openapi_v2.json).
- Source modules:
  - `src/analysis/scoring_engine.py` — orchestrator + M3 sub-scores + signal logic
  - `src/analysis/sector_percentile.py` — sector-relative percentile ranks (M3)
  - `src/analysis/quality_signals.py` — real Piotroski + Altman Z'' (M4)
  - `src/analysis/earnings_quality.py` — Beneish, Sloan, CCR (M5)
  - `src/analysis/quality_moat.py` — Gross profitability, ROIC stability, moat (M5)
  - `src/analysis/risk_metrics.py` — vol, drawdown, real risk (M5)
  - `src/analysis/dcf.py` — two-stage DCF + sensitivity (M6)
  - `src/analysis/horizon_scoring.py` — three-horizon composites + gates (M7)
  - `src/analysis/momentum.py` / `revisions.py` / `sentiment.py` — momentum + revisions + FinBERT (M9)
  - `src/strategy/screener.py` + `src/strategy/horizon_presets.py` — 9 presets + universal pre-filters (M8)
  - `backend/app/services/market_data/` — Protocol + FMP + yfinance + hybrid (M2)
  - `backend/app/services/backtest/walk_forward.py` — backtest framework (M12)
