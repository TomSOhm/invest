# Backtest methodology -- M12 v0

This document describes the assumptions, biases, and known limitations of
the walk-forward backtest framework introduced in M12.

## Scope

The backtest framework validates each of the 9 horizon presets defined in
`src.strategy.horizon_presets.PRESET_REGISTRY` against an appropriate
benchmark over a configurable time window. For M12 the typical window is
2020-01-01 → 2024-12-31 (5 years, kept short to keep CI runtime sane).

## Mechanics

At each rebalance date (default = quarter-end):

1. The full universe DataFrame is scored via
   `src.analysis.scoring_engine.score_dataframe`, with the trailing-window
   price history threaded in for momentum signals.
2. The named horizon preset's filter dict is applied via
   `src.strategy.horizon_presets.screen_horizon_preset`.
3. The surviving names are equal-weighted and capped at `max_position_size`
   (default 10%, i.e. ≤10 names).
4. The basket is held until the next rebalance date.
5. A flat `transaction_cost` (default 10 bp) is debited per rebalance
   turnover.

## Acknowledged biases (v0)

### Look-ahead bias

The framework uses **current-snapshot fundamentals** as a proxy for the
scoring inputs at every historical rebalance date. This means the scoring
engine sees the *current* P/E, ROIC, F-Score, etc. when it ranks names for
a 2020-Q1 rebalance.

This is the largest single source of bias in v0. The bias inflates apparent
alpha for any preset whose stocks have improved fundamentals between the
backtest start and today (winners tend to look better in the rear-view
mirror). A symmetric inflation occurs in the opposite direction for
deteriorating businesses.

**Mitigation roadmap (M14+)**: fetch FMP's point-in-time annual + quarterly
fundamentals per ticker per rebalance date and re-score the universe with
the period-correct snapshot. Costs ~1 FMP call per ticker per rebalance per
financial statement type, so a 50-ticker universe with 20 rebalances over
5 years is ~3000 FMP calls -- well within the daily 250-call free-tier
budget if amortised across days, but tight in a single batch run.

### Survivorship bias

The universe ticker list is **fixed at construction**. Any company that has
been delisted, acquired, or had a material corporate action between the
backtest start and today is silently absent from earlier rebalances.

**Mitigation roadmap**: source a point-in-time index membership history
(CAC 40 / S&P 500). For PEA the official Euronext 2025-05-15 list is
already in `docs/Euronext_Equities_2025-05-15.csv`; we'd need to build a
"trade history" of additions / removals.

### Cost model

A flat **10 bp round-trip** transaction cost is debited on every rebalance
turnover. The actual cost depends on:

- **Bid-ask spread**: typically 5-15 bp for liquid CAC 40 / S&P 500 names,
  much wider for small caps.
- **Slippage**: meaningful when basket size is comparable to daily volume.
- **Commission**: ~0.1-0.3% on retail PEA brokers (Bourse Direct, Saxo);
  effectively zero on US discount brokers.

The 10 bp assumption is a reasonable midpoint for liquid-only baskets but
will *understate* costs for any preset that pulls in micro-caps.

### Cash bucket

When the preset's `max_position_size` cap forces the basket below 100%
investment (e.g. 5 names × 10% = 50% invested), the residual sits in cash
**earning 0%**. This is conservative when rates are low (most of the
2018-2024 window), generous when rates are high (2023-2024).

### Benchmark choice

- PEA presets: CAC 40 (`^FCHI`) -- price-only, no dividends reinvested.
- Global presets: S&P 500 (`^GSPC`) -- price-only, no dividends reinvested.

Both benchmarks ignore dividends, matching the price-only treatment of the
individual constituents. A dividend-adjusted comparison would slightly
favour the strategies (which hold actual dividend-paying stocks but report
price-only equity curves) -- this asymmetry is a small bias *against*
strategies with high yields.

## Statistical caveats

- 5 years of monthly / quarterly observations gives ~20-60 data points,
  which is **far below** the sample size needed to reject the null of
  zero alpha at conventional significance levels. The reported alpha
  numbers are descriptive, not inferential.
- Regression-based alpha and beta use OLS without HAC adjustment;
  serial correlation in returns is ignored.
- The Sharpe ratio uses an annualised constant of √252; for monthly /
  quarterly rebalanced strategies the daily series under-counts the
  effective sample.

## Future work

- M14: point-in-time fundamentals (eliminates look-ahead bias).
- M15: Monte Carlo bootstrap on the equity curve to attach confidence
  intervals to alpha / Sharpe.
- M16: factor-attribution analysis (Fama-French 5-factor + momentum) to
  decompose preset returns into known risk premia.
