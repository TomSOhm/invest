# ADR 0003: Sector-Relative Percentile Rank

**Status:** Accepted
**Date:** 2026-05-08
**Authors:** Tom S, Claude (Opus 4.7)

---

## Context

The v1 scoring engine had a function called `_percentile_score` (`src/analysis/scoring_engine.py:31` in the v1 codebase) used to map raw metrics (P/E, P/B, ROE, margins, etc.) to a 0–100 sub-score. The name implied a percentile rank — a company at the 50th percentile of its peer set scores 50.

But the implementation was **not** a percentile rank. It was a linear interpolation between two hardcoded bounds:

```python
def _percentile_score(value, low_bad=5, high_good=30):
    """100 if value >= high_good, 0 if value <= low_bad, linear in between."""
    if value <= low_bad: return 0
    if value >= high_good: return 100
    return (value - low_bad) / (high_good - low_bad) * 100
```

Per the 2026-05-08 audit (§1.5):

> The function name suggests a rank-based scoring (where the company's position relative to peers determines the score), but the implementation is a **linear interpolation between two hardcoded bounds**. This means:
>
> - A software company at P/E 35 scores poorly even though it's cheaper than its sector median (40+).
> - A utility at P/E 14 scores poorly even though it's more expensive than its sector median (12).
> - The score is **not** comparable across sectors — yet the screener sorts by composite across the entire universe.

Concrete example:

- A SaaS company at P/E 35: scored ~0 by the linear map (clamped at the cheap-end), even though P/E 35 is *below* the software-sector median (~40+).
- A utility at P/E 14: scored ~80 by the linear map (close to the high-good of 30 reversed), even though P/E 14 is *richer* than the utility-sector median (~12).

Both verdicts are wrong relative to peers. The composite score then aggregates these wrong values and ranks across the entire universe — meaning sector composition silently dominates the ranking. Software and biotech names systematically score low; utilities and financials systematically score high. Nothing the user does to the weights can fix this; the inputs are biased.

The audit's recommendation (§1.5):

> Switch to **sector-relative percentile ranks** using `df.groupby('Sector')[metric].rank(pct=True)`.

---

## Decision

Replace `_percentile_score(value, low_bad, high_good)` with `score_sector_relative(df, metric, inverse=False, min_n=5)` (`src/analysis/sector_percentile.py`):

```python
def score_sector_relative(df, metric, inverse=False, sector_col="Sector", min_n=5):
    """For each sector with >= min_n non-NaN peers, return 0..100 percentile
    rank within sector. Sectors below the peer floor fall back to global rank.
    Higher rank = higher score, except inverse=True flips it (P/E lower-is-better).
    NaN inputs preserve NaN — no imputation."""
```

The implementation uses pandas' built-in `rank(method="average", pct=True, na_option="keep")` and multiplies by 100 to get a 0–100 score. For `inverse=True` (cheaper-is-better metrics like P/E, EV/EBITDA, DebtEquity), the rank is flipped via `100 - ranked`.

For sectors with fewer than `min_n` non-NaN peers (default 5), the rank falls through to the **global** universe — better an approximate global rank than an unstable 1-or-2-peer sector rank.

The function preserves the input DataFrame's index and **never imputes NaN**. A ticker missing P/E gets a NaN score for the P/E component, which the M7 weighted mean drops out of both the numerator and denominator (`src/analysis/horizon_scoring.py`, `_renormalised_weighted_mean`).

This module is consumed by every M3+ sub-score generator (`valuation_score_df`, `profitability_score_df`, `health_score_df`, `growth_score_df`, etc.) and the M5 modules (`earnings_quality_score`, `moat_score`, `risk_score_real`).

---

## Consequences

### Positive

- **Cross-sector comparability is restored**. A SaaS at the 60th percentile of software is meaningfully comparable to a utility at the 60th percentile of utilities. Composite ranking is no longer dominated by sector composition.
- **No magic numbers**. The breakpoints (`low_bad=5`, `high_good=30`) used to be embedded per-metric in the v1 code; v2 has none. The metric-to-rank mapping is determined by the data itself.
- **Robust to outliers**. Percentile rank is unaffected by extreme values (a company with P/E 500 still scores at the bottom of its sector — same as P/E 100 or 200). The linear map's clamp behaviour was implicit; rank's clamp is explicit (always [0, 100]).
- **NaN-safe**. Missing inputs preserve NaN — no fabrication. See [ADR-0004](0004-no-fabricated-values.md).
- **Sector-fallback prevents pathology**. With `min_n=5`, a sector with 2 peers doesn't produce extreme 0/100 scores; it falls back to global rank. Tested in `tests/test_sector_percentile.py::test_small_sector_falls_back_to_global`.
- **Pure function, easy to test**. No I/O, no state. The module's 11 tests in `tests/test_sector_percentile.py` cover the within-sector rank, fallback, NaN preservation, inverse flip, and edge cases (empty sector label, missing column).

### Negative / trade-offs

- **Universe-dependence**. A ticker's score depends on the rest of the universe. The same company gets a different score in a 10-stock universe than in a 200-stock universe. This is *correct behaviour* for a relative metric, but it makes the scores less stable across runs that change universe size.
- **Sector taxonomy fragility**. The whole approach depends on `Sector` being correctly populated. FMP and yfinance disagree on some sectors (GICS vs Yahoo's taxonomy) — see [ADR-0002](0002-fmp-yfinance-hybrid.md). A name with the wrong sector label gets ranked against the wrong peers. Tracked in the coverage matrix.
- **Sector-fallback floor (`min_n=5`) is heuristic**. The number is justifiable (5 peers gives at least minimal ranking signal) but isn't backed by a backtest. Edge cases (small sectors with 4 peers right at the boundary) sometimes flip between sector and global ranking. Acceptable; documented.
- **Loss of absolute interpretability**. v1's "P/E < 15 → score 75" was easy to explain. v2's "P/E at 35th percentile → score 35" requires the reader to know what the sector median P/E is. Mitigated by the frontend showing both the score and the raw metric.
- **Negative-PE edge case**. Companies with negative P/E (loss-making) can't be meaningfully ranked alongside positive-P/E peers. The module assigns them a fixed `_NEGATIVE_PE_PENALTY = 10.0` post-rank override. This is one of the few remaining "hardcoded" decisions; it's documented inline and accepted as an acceptable simplification.
- **First-time-user surprise**. Running the engine with a 3-stock universe produces "scores" that all cluster around 33/66/100 because there's nothing to rank against. Documentation calls this out; minimum recommended universe size is ~30 names (the sample universe).

---

## Alternatives considered

### Alternative 1: Keep linear map but compute sector medians dynamically

**Rejected because** it's still a linear map, just with sector-aware breakpoints. The "score = 0 if below sector floor" behaviour is the wrong shape — a name 5% below the sector median is barely different from one at the median, but a linear map would give them different scores. Percentile rank handles this correctly.

### Alternative 2: Sector z-score (normalised by sector mean and stddev)

**Considered seriously**. Has a clean theoretical basis (assumes normal-ish distribution within sector). Rejected for two reasons:
1. **Outliers**: a single mega-cap outlier (e.g. NVDA at P/E 80 pulling Tech up) skews the mean and stddev, distorting every other ticker's score. Percentile rank is robust to outliers.
2. **Sample size**: with 5–20 peers per sector, the mean and stddev are noisy estimates. Rank uses all the order information without needing to estimate moments.

The audit also briefly suggested z-scores with **MAD** (median absolute deviation) for robustness; that's a viable middle ground, but percentile rank is simpler and has identical robustness properties for the use case.

### Alternative 3: Hybrid — percentile rank for valuation, linear for absolute thresholds

**Considered**. Some metrics genuinely have absolute thresholds (e.g. "ROIC must be > 12% to be quality"). The decision was: keep absolute thresholds as **gates** in the screener (`min_roic: 0.12` in `LT_QUALITY_COMPOUNDER`) and use sector-relative ranks for **scoring**. This separates "investability" (absolute thresholds, binary pass/fail) from "ranking" (relative scores, continuous 0–100). Both layers coexist in v2 and serve different purposes.

### Alternative 4: Industry-relative instead of sector-relative

**Rejected for now**. Industry granularity (e.g. "Semiconductor Equipment & Materials" vs broader "Technology") is more precise but reduces peer count drastically — a ticker in a small industry has 0–3 peers and falls back to global ranking anyway. Sector-level ranking gives the best balance of relevance and statistical stability with current universe sizes. Industry ranking is a candidate for M14+ when paid-tier data widens the universe.

---

## References

- Audit: research vault, `AUDIT_2026-05-08_Screener_Metrics.md` §1.5 ("`_percentile_score` is misnamed"), §2.3 (multi-input valuation problems), §4 ("Replace single linear `_percentile_score` with sector-relative percentile rank").
- Methodology v2: research vault, `METHODOLOGY_v2.md` §2 ("Sector-relative scoring (high-leverage change)").
- Implementation:
  - `src/analysis/sector_percentile.py` — `score_sector_relative` and `_percentile_rank`.
  - `src/analysis/scoring_engine.py` — `valuation_score_df`, `profitability_score_df`, etc. all consume `score_sector_relative`.
  - `tests/test_sector_percentile.py` — 11 tests covering within-sector rank, fallback, inverse, NaN preservation, edge cases.
- Companion ADRs: [0001](0001-three-horizon-scoring.md) (the horizon abstraction that consumes these sub-scores), [0004](0004-no-fabricated-values.md) (NaN preservation policy).
