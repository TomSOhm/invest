# ADR 0004: NaN over Fabricated Values

**Status:** Accepted
**Date:** 2026-05-08
**Authors:** Tom S, Claude (Opus 4.7)

---

## Context

The v1 data fetcher and scoring engine quietly substituted invented numbers when source data was missing. The 2026-05-08 audit catalogued seven critical instances:

### 1. EBIT aliased to EBITDA

`backend/app/services/data_fetcher.py:132,196` (v1):

```python
result["EBIT"] = _safe_get(info, "ebitda", np.nan)  # yfinance often lacks EBIT separately
ebit_val = _safe_get(info, "ebitda", np.nan)  # proxy
```

Per audit §1.1: ROIC inflates by D&A / Invested Capital (typically +2–5pp for industrials, more for telcos). Altman X3 = EBIT/Assets becomes EBITDA/Assets, over-stating financial health for capital-intensive businesses. Composite "profitability" score is biased upward across utilities, telcos, oil & gas, manufacturing.

### 2. Fabricated interest expense

`data_fetcher.py:220` (v1):

```python
interest_expense = _safe_get(info, "totalDebt", 0) * 0.04  # rough 4% rate assumption
```

Per audit §1.2: a 4% blanket cost of debt over-estimates expense for prime-rated names (Nestlé, ASML borrow at 1–2%) and under-estimates it for high-yield issuers (Atos, distressed names borrow at 8–12%). InterestCoverage becomes orthogonal to actual coverage. Strict PEA filter `min_interest_coverage = 3.0` is then triggered by an artifact, not the real ratio.

### 3. Piotroski signal #7 awarded by default

`scoring_engine.py:215` (v1):

```python
# 7. No dilution (proxy: shares stable) — award by default
score += 1
```

Per audit §1.3: this *unconditionally* added +1. Over the universe, every name got at least 1/9 free. The score was inflated and signal-less on this dimension.

### 4. Piotroski D/E inverted default

`scoring_engine.py:205` (v1):

```python
# 4. CFO > Net Income (accruals quality)
if row.get("OperatingCashflow", 0) > row.get("NetIncome", float('inf')): score += 1
```

When `NetIncome` was missing, the default was `+inf` → the comparison always evaluated False, so no point was awarded. Reverse logic intended.

### 5. Altman Z fabricated working capital and retained earnings

`scoring_engine.py:233-237` (v1):

```python
wc = row.get("Cash", 0) - row.get("TotalDebt", 0) * 0.3      # WC proxy
x2 = (eq * 0.4) / ta                                          # RE proxy
```

Per audit §1.4: WC = Current Assets − Current Liabilities, **not** `cash − 0.3 × debt`. A retailer with high inventory and low cash gets WC severely understated; a tech company sitting on cash gets it severely overstated. Retained earnings as 40% of equity is a flat heuristic that's wildly wrong for young IPOs (low RE, high paid-in capital), buyback-heavy mature names (negative RE/equity), and companies with preferred stock.

### 6. `_percentile_score` linear-mapped, mislabelled as percentile

Detail in [ADR-0003](0003-sector-relative-percentile.md). Not strictly a fabrication, but mislabelled as one type of score and computed as another. Same family of silent corruption.

### 7. DCF documented but never implemented

Per audit §1.6: `METHODOLOGY.md` v1 devoted most space to DCF, the brief listed `dcf_model.py` and `valuation.py` in the architecture, and the signal logic depended on `Price < 70% of intrinsic value`. **No DCF code existed.** Only `graham_number()` was implemented. The "Strong Buy" signal could never trigger correctly because it needed an intrinsic value that was never computed.

The "Strong Buy" gate read `min_price_to_intrinsic: 0.70` from settings.yaml, but the comparison operand was always missing, silently failing — every name got the legacy composite-only fallback path.

### 8. Settings declared but not wired

Per audit §2.7: `screener.exclude_sectors`, `screener.min_avg_volume`, `screener.min_years_listed` were loaded into settings but never applied in `apply_filters()`. Tobacco/gambling exclusion silently failed; small-caps with thin liquidity passed; freshly-IPO'd names with 9-month history passed.

---

## Decision

Adopt a strict **no-fabrication policy**:

> When the source data is missing, the engine returns NaN. It does not invent a proxy. It does not substitute a neutral value. It does not silently award default points. The value is propagated as NaN through the pipeline, and the consumer (M7 horizon scoring, screener gates, frontend display) handles it explicitly.

Concrete commitments:

1. **Real EBIT** (M1, M2). Pull from `tk.financials.loc['EBIT']` (yfinance) or FMP `/income-statement` `operatingIncome`. NaN if both miss. No fallback to EBITDA.

2. **Real interest expense** (M1, M2). Pull from income statement (`tk.financials.loc['Interest Expense']` or FMP `interestExpense`). NaN if both miss. The 4% × debt fabrication is deleted.

3. **Real Piotroski deltas** (M4). Fetch 2 fiscal years of statements. Compute true year-over-year deltas for ROA, leverage, current ratio, gross margin, asset turnover. Use `tk.get_shares_full()` for actual share-count change to detect dilution (>0.5% increase = no point). The unconditional "free point" for signal #7 is deleted. Each individual signal helper returns `1 / 0 / None`; the aggregator sums non-None signals — a company with 6 of 9 signals computable scores 0–6, not 0–9 (matches Piotroski 2000's data-completeness handling).

4. **Real Altman Z'' inputs** (M4). Pull `CurrentAssets`, `CurrentLiabilities`, `RetainedEarnings` from the balance sheet. Compute `WC = CurrentAssets − CurrentLiabilities` directly. Use `RetainedEarnings` directly. Sector-aware dispatch: classic 5-factor Z for manufacturers, Z'' (4-factor, no asset turnover) for everyone else.

5. **Sector-relative percentile** (M3). See [ADR-0003](0003-sector-relative-percentile.md). NaN inputs preserve NaN; sector-relative rank computes only over present values.

6. **Real DCF** (M6). Two-stage with sensitivity grid. When inputs are missing (FCF margin undefined for banks, shares unknown, etc.), the function returns `{"intrinsic_mid": NaN, "warnings": ["..."]}` rather than guessing. The `generate_signal` function handles NaN MoS gracefully — falls back to legacy composite-only thresholds.

7. **Wire the unused screener filters** (M1, M8). `exclude_sectors`, `min_avg_volume × price`, `min_years_listed` are now actually applied in `apply_filters()`. Universal pre-filters in `_UNIVERSAL_PREFILTERS` (`src/strategy/horizon_presets.py`) include all three.

8. **NaN propagation policy in scoring**. The M7 weighted mean (`_renormalised_weighted_mean`) drops NaN sub-scores from BOTH the numerator and denominator, renormalising over the present categories. A name with 5 of 8 sub-scores still scores correctly. A name with 0 of 8 returns NaN composite, which the legacy 50.0 fallback maps to "Hold" rather than crashing.

9. **NaN propagation policy in gates**. When a gate's input is NaN, the gate fails with `missing_<key>` (e.g. `missing_altman_z`, `missing_market_cap`). This is conservative: a name we can't evaluate is excluded, not silently passed. Tested in `tests/test_horizon_scoring.py`.

10. **NaN propagation policy in API**. Backend Pydantic models use `Optional[float]` for every nullable field. JSON responses serialise NaN as `null`. Frontend renders `—` for null values rather than `0` or `NaN`.

---

## Consequences

### Positive

- **Honesty**. The engine no longer reports plausible-looking numbers that are actually fabricated. A NaN ROIC tells the user "we don't know"; a fabricated ROIC tells them confidently the wrong thing.
- **Bug elimination**. The seven audit-flagged corruptions are gone. EBIT is EBIT, not EBITDA. Interest expense is real or NaN. Piotroski signals reflect actual year-over-year improvement. Altman Z uses real working capital and retained earnings.
- **Conservative defaults**. NaN gates fail closed (the name is excluded). A user can't be misled into buying a name whose evaluation we couldn't actually do.
- **`data_completeness` is meaningful**. The 0.0–1.0 fraction reflects what's genuinely present, not what we patched over with proxies. The horizon gates (`min_data_completeness`) accept different thresholds per horizon — LT requires 0.70 (no shortcuts on long holds), ST relaxes to 0.50 (momentum-driven, fewer fundamentals needed).
- **Trustable backtests**. The M12 backtest is computed on real numbers (where they exist) plus NaN-skip on missing rows. The reported alpha isn't inflated by names whose Z-scores were fabrications.
- **Auditable provenance**. Combined with the M2 `field_sources` audit trail, every numeric in the engine has a known origin: FMP, yfinance, or "missing".

### Negative / trade-offs

- **More NaN handling code everywhere**. Every aggregator must check for NaN and decide whether to skip, default, or propagate. Mitigated by helper functions (`_is_finite`, `_to_float`, `_safe_div`) used consistently across modules.
- **Smaller scorable universe**. Some EU mid-caps that "scored" in v1 (via fabricated proxies) now score NaN in v2 because their true data isn't available. This is **correct** but reduces apparent universe coverage. Mitigated by the FMP+yfinance hybrid (see [ADR-0002](0002-fmp-yfinance-hybrid.md)) which fills more fields than yfinance alone.
- **More tests required**. Each module needs explicit "missing input → NaN" tests. The test suite grew from ~120 to ~400 tests, partly to lock in NaN behaviour.
- **Information density on UI**. A row with several NaN cells looks "incomplete" to a user used to seeing every cell filled. The frontend's design has to accommodate empty cells gracefully (we use `—` and add tooltips explaining `data_completeness`).
- **Edge case: legacy Composite_Score fallback**. To preserve snapshot-test backwards compatibility (M0 golden files), `compute_composite_score` still returns 50 when every sub-score is NaN. M14 will remove this fallback once the snapshots are regenerated.
- **Edge case: `_NEGATIVE_PE_PENALTY = 10.0`**. Loss-making companies (negative P/E) can't be ranked against positive-P/E peers; we assign a fixed score. This is one of the few remaining "magic numbers" — explicitly documented as a simplifying assumption rather than a fabrication.
- **Onboarding friction**. New contributors expect "default = 0" or "default = mean"; the discipline of "default = NaN" needs to be taught and reinforced in code review.

---

## Alternatives considered

### Alternative 1: Keep proxies but document them transparently

**Rejected because** the documentation is a poor substitute for correct numbers. A note "EBIT is approximated by EBITDA" doesn't prevent ROIC from being inflated by D&A in every downstream consumer. Documentation lives elsewhere from the data; users who skim straight to the score will see a confidence number that doesn't reflect the underlying corruption.

### Alternative 2: Replace bad proxies with better proxies

**Rejected because** the audit's fundamental critique was that proxies are silent corruption regardless of how good they are. A 25% D&A-as-fraction-of-EBITDA proxy for EBIT is better than the 100% identity, but it's still a fabrication. The right answer is: get the real number from a source that has it, or report NaN.

### Alternative 3: NaN by default, but have a `--allow-proxies` mode for quick exploration

**Rejected because** modes are dangerous in scoring engines. A "demo" mode that uses proxies could leak into production by accident. The discipline of "always real, NaN otherwise" is simpler to reason about and harder to misuse.

### Alternative 4: Distinguish "soft NaN" (we tried but couldn't) from "hard NaN" (not applicable)

**Considered briefly**. A bank's FCF margin is "not applicable" (banks don't report FCF the same way industrials do); a small-cap's M-Score is "we tried but the prior-year data isn't there". The two are conceptually different. Decided against the distinction for v2 — the consumer (gates, frontend) treats both as missing, and the `field_sources` audit trail (`"missing"` vs `"yfinance"`) already captures most of the information.

---

## References

- Audit: research vault, `AUDIT_2026-05-08_Screener_Metrics.md` §1 (all seven critical bugs), §2.7 (settings.yaml fields wired but unused), §3 (what to remove).
- M1 commit: `cec0856 fix(scoring): eliminate critical bugs in scoring engine and data layer (M1)` — eliminates the seven fabrications.
- Implementation:
  - `src/analysis/quality_signals.py` — Piotroski signals 1–9, each returning `1 / 0 / None` (no free points).
  - `src/analysis/quality_signals.py` — `altman_z_select` reads real WC, RE, EBIT.
  - `src/analysis/dcf.py` — DCF returns `{intrinsic_mid: NaN, warnings: [...]}` when inputs are missing (M6).
  - `src/analysis/horizon_scoring.py` — `_renormalised_weighted_mean` drops NaN sub-scores; `_check_gates` reports `missing_<key>` for NaN gate inputs.
  - `src/strategy/horizon_presets.py` `_UNIVERSAL_PREFILTERS` — the formerly-unused settings (`exclude_sectors`, `min_avg_daily_volume_eur`, `min_years_listed`) are now applied.
  - `backend/app/services/market_data/hybrid_fetcher.py` — `field_sources` audit trail; "missing" attribution for fields neither source provides.
- Companion ADRs: [0002](0002-fmp-yfinance-hybrid.md) (the data layer that produces real values), [0003](0003-sector-relative-percentile.md) (NaN-preserving rank function).
