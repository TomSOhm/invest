# ADR 0001: Three-Horizon Scoring

**Status:** Accepted
**Date:** 2026-05-08
**Authors:** Tom S, Claude (Opus 4.7)

---

## Context

The v1 engine emitted a **single** composite score (0–100) and a **single** signal (Strong Buy → Strong Sell) per ticker. The same number was used to decide whether to buy a long-term compounder, a medium-term re-rating play, or a short-term momentum trade.

The 2026-05-08 audit (research vault, `AUDIT_2026-05-08_Screener_Metrics.md` §2.8) called this out as a structural error:

> Single signal regardless of horizon. `generate_signal()` returns one verdict (Strong Buy → Strong Sell). A "Buy" for a long-term compounder (Hermès, ASML) and a "Buy" for a momentum-driven re-rating play (post-earnings beat with rising estimates) are very different — and require different thresholds, position sizes, and exit rules.

Concretely:

- **LT decisions** weight quality and earnings-integrity heavily. Multi-year ROIC stability, real Piotroski F-Score, Altman Z'' safe zone, sector-relative valuation cap, DCF margin of safety.
- **MT decisions** weight catalyst signals: forward earnings revisions, op margin expansion, deleveraging, technical confirmation. Hold periods of 1–3 years.
- **ST decisions** are dominated by momentum, volume surge, SUE, sentiment. Hold periods of weeks to a few months. The value of trailing 5y CAGRs collapses.

Hard-coding one weight scheme to satisfy all three horizons systematically over-weights the wrong inputs for two out of three. A short-term momentum trade was being held to the same DCF MoS bar as a 10-year hold; a long-term compounder was being downgraded for failing a momentum check it didn't need.

The audit also noted a tax-and-account dimension specific to this project: a French investor running a PEA cannot trade short-term frequently without forfeiting the tax wrapper. Surfacing the same Buy signal whether the holding is appropriate for a PEA or a CTO leaves the user to figure out themselves which signal to act on inside which account.

---

## Decision

Replace the single composite + signal with **three independent composites** and **three signals** per ticker, each parameterised by its own weight vector and gate set:

```
score_lt, signal_lt, passes_gates_lt, blockers_lt   (long-term, 5y+)
score_mt, signal_mt, passes_gates_mt, blockers_mt   (medium-term, 1–3y)
score_st, signal_st, passes_gates_st, blockers_st   (short-term, <6mo)
```

Per-horizon configuration lives in `settings.yaml` `horizons:` and is consumed directly by `src/analysis/horizon_scoring.py`:

```yaml
horizons:
  long_term:
    weights:
      valuation: 0.20
      profitability: 0.25
      health: 0.15
      earnings_quality: 0.10
      growth: 0.10
      capital_allocation: 0.10
      risk: 0.10
    gates:
      min_data_completeness: 0.70
      max_distress: 1.1
      min_market_cap: 100000000
      min_years_listed: 3
  medium_term:
    weights: { ..., momentum: 0.10 }
    gates: { ... }
  short_term:
    weights: { momentum: 0.55, ... }
    gates:
      min_data_completeness: 0.50
      max_distress: 1.5
      min_market_cap: 500000000
      min_avg_volume: 2000000
      max_realized_vol_1y: 0.5
      pea_warning: true
      recommended_account: "CTO"
```

Implementation is centralised in `src/analysis/horizon_scoring.py` with three thin wrappers (`score_long_term`, `score_medium_term`, `score_short_term`) sharing one internal `_score_one_horizon` helper. Composites are computed via a renormalised weighted mean (`_renormalised_weighted_mean`) so missing sub-scores drop out of both the numerator and denominator rather than being silently substituted with a neutral 50.

The signal-generation function `generate_signal(composite, mos)` activates the M6 two-criterion path (composite + DCF margin-of-safety) when MoS is finite, falling back to legacy composite-only thresholds when DCF is unavailable. Each horizon receives the same `mos` input but applies it against its own composite.

ST presets carry `recommended_account: "CTO"` metadata, which propagates to the `score_three_horizons` output so the frontend renders a `<CTOWarningBanner>` whenever a PEA-eligible name shows a passing ST signal.

---

## Consequences

### Positive

- Each horizon now has a **defensible weight scheme** matched to the holding period. LT values quality, ST values momentum, MT bridges them.
- The **gate set** can also vary per horizon — ST's 0.50 data-completeness threshold accepts sparser names than LT's 0.70, but ST tightens liquidity (`min_avg_volume: 2M`) and volatility (`max_realized_vol_1y: 0.5`) where LT relaxes them.
- The **PEA caveat** is structurally encoded. ST signals on PEA-eligible names trigger a CTO recommendation rather than silently encouraging a tax-wrapper-busting trade.
- Adding a fourth horizon (e.g. "intraday") would be a configuration change, not a code change. The horizon abstraction is mechanically extensible.
- Single-source-of-truth: `settings.yaml` controls weights and gates. No magic numbers buried in code.
- **Honest reporting**: a `blockers_st: ["max_realized_vol_1y", "missing_momentum"]` tells the user *why* a name fails ST, instead of presenting a misleading 50.0 fallback score.

### Negative / trade-offs

- **More API surface**. Every consumer (frontend, screener, portfolio, backtest) now handles three scores instead of one. The legacy `composite_score` field is removed entirely (atomic v2 schema replacement — see [ADR-0005](0005-atomic-frontend-backend-schema-replacement.md)).
- **More test surface**. Each horizon has its own snapshot tests, gate tests, signal tests. Test count grew from ~120 (v1) to ~400 (v2).
- **More config surface**. `settings.yaml` `horizons:` block is denser than the original `scoring:` weights — three weight maps, three gate maps. Mitigated by inline comments and the fact that the defaults rarely need user tuning.
- **Cognitive load** on the user. The dashboard now shows three scores per ticker, which can confuse a first-time user. Mitigated by the `<HorizonSelector>` component (M11) which lets the user pick a "primary" horizon at the page level.
- **Backtest framework complexity** (M12). Each preset is tied to one horizon, which simplifies the backtest, but the `score_dataframe` call must produce all three horizon scores at every rebalance — non-trivial for picking the right benchmark, since CAC 40 is appropriate for PEA presets while S&P 500 fits global presets.

---

## Alternatives considered

### Alternative 1: Keep one composite, vary the *signal thresholds* by horizon

**Rejected because** it doesn't solve the underlying problem. The composite would still be a single weighted mean, dominated by whichever weights were chosen. Tuning thresholds downstream just moves the bias around. A high-momentum, mediocre-quality name would still score the same as a high-quality, low-momentum name — and that's not a horizon-correct comparison.

### Alternative 2: One composite + a "horizon attribute" tag (LT/MT/ST) per ticker

**Rejected because** a single ticker can be a great LT compounder *and* a hot ST momentum play simultaneously (e.g. NVIDIA in late 2023). Forcing a single tag erases that information. The whole point of the three-horizon model is that different horizons can give different signals on the same ticker.

### Alternative 3: Run three separate scoring engines, each loaded with its own settings

**Rejected because** of the duplication. The 8 sub-scores (Valuation, Profitability, Health, Growth, Capital Allocation, Risk, Earnings Quality, Moat, plus Momentum) are the same across horizons; only the *weighting* and the *gates* change. Computing the sub-scores three times is wasteful, and keeping three implementations in sync is a maintenance burden.

### Alternative 4: Compute one composite, then compute three "adjusted" composites by post-hoc weight shuffling

**Rejected because** it conflates two design decisions. Sub-score normalisation (sector-relative ranks) needs to happen once across the universe; horizon-specific weighting needs to happen per-row after that. Post-hoc shuffling against a pre-computed composite would require unwinding the sub-score weights, which is mathematically equivalent to the chosen approach but clumsier in code.

---

## References

- Audit findings: research vault, `AUDIT_2026-05-08_Screener_Metrics.md` §2.8 ("Single signal regardless of horizon").
- Methodology v2: research vault, `METHODOLOGY_v2.md` §2 (composite weighting per horizon), §11 (output: three signals, not one).
- Horizon configurations: research vault, `HORIZON_CONFIGS.md` (the explicit LT / MT / ST screener presets that drove preset-design discussion).
- Implementation:
  - `src/analysis/horizon_scoring.py` — the three-horizon orchestrator.
  - `settings.yaml` `horizons:` block — per-horizon weights and gates.
  - `src/strategy/horizon_presets.py` — 9 named presets (3 per horizon).
  - `backend/app/models/horizons.py` — Pydantic schema for horizon outputs.
  - `frontend/src/components/ui/HorizonSelector.tsx`, `HorizonScoreCard.tsx`, `CTOWarningBanner.tsx` — UI surface.
- Companion ADRs: [0003](0003-sector-relative-percentile.md) (sub-score normalisation), [0005](0005-atomic-frontend-backend-schema-replacement.md) (schema migration).
