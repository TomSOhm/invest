# Changelog

All notable changes to Invest Solo are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The v2 release (M0–M12, captured in `[0.4.0]` below) is a near-complete rewrite of the scoring engine driven by the 2026-05-08 audit. Each milestone (M0–M13) lands a single, focused commit; this changelog summarises the cumulative effect at the v0.4.0 marker.

---

## [Unreleased] — Public Release Prep

### Added
- `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1 reference).
- `.github/ISSUE_TEMPLATE/{bug_report.md, feature_request.md, config.yml}` — issue templates with structured fields, blank issues disabled, contact links to Discussions and docs.
- `.github/PULL_REQUEST_TEMPLATE.md` — type-of-change checkboxes, related-issues field, CI/secrets/CHANGELOG checklist.
- `.github/dependabot.yml` — daily updates for `pip` (`/`), `npm` (`/frontend`), weekly for `github-actions` (`/`); minor+patch grouped.
- Full GitHub Actions CI pipeline under `.github/workflows/`:
  - `test-backend.yml` — pytest matrix on Python 3.11/3.12 with `uv sync --frozen`
  - `lint-backend.yml` — ruff check + ruff format
  - `frontend.yml` — Node 24 `npm ci && npm run lint && npm run build`
  - `codeql.yml` — Python + JavaScript/TypeScript, weekly schedule
  - `gitleaks.yml` — secret scanning on push and PR
- README CI status badges (test, lint, frontend, CodeQL) and Community section (CoC, Contributing, Discussions, Security disclosure link).
- `ruff` added to `[dependency-groups] dev` in `pyproject.toml`; `[tool.ruff]` config with `line-length = 120`, target `py311`, lint rules `E,F,I,W,B,UP`.

### Changed
- Parameterized hardcoded `/home/claude/invest/` demo paths in `src/reporting/{chart_generator,dashboard_generator,excel_export}.py` to use repo-relative `data/` via `pathlib.Path(__file__).resolve().parents[2]`.

### Removed
- Untracked `.claude/` (155 files: agents, skills, fonts, configs) from git index — files remain on disk locally, gitignored.
- Untracked `data/results_17022026/` (7 sample binary outputs) from git index — gitignored.

### Security
- Git commit history rewritten via `git filter-repo`: maintainer email migrated to GitHub noreply (`195091248+TomSOhm@users.noreply.github.com`) across all commits; accidentally-tracked binary outputs and local Claude config purged from full history.

---

## [Previously Unreleased]

### Added
- M13: full documentation refresh — METHODOLOGY v2, DATA_SOURCES v2, PROJECT_BRIEF v2, 5 ADRs, CHANGELOG.

---

## [0.4.0] — 2026-05-08 — v2 release

### Added

**Scoring engine**

- **M0** — Golden-file regression harness for the v1 scoring engine (`tests/test_scoring_snapshot.py`, `tests/golden/`). Captures the v1 outputs as a baseline so v2 changes are visible at PR time.
- **M3** — Sector-relative percentile scoring (`src/analysis/sector_percentile.py`). Replaces the linear `_percentile_score` map with `df.groupby(Sector)[metric].rank(pct=True) * 100`. Sectors with fewer than 5 peers fall back to global rank. NaN inputs preserve NaN. See [ADR-0003](docs/adr/0003-sector-relative-percentile.md).
- **M4** — Real Piotroski F-Score and sector-aware Altman Z / Z'' (`src/analysis/quality_signals.py`). Each Piotroski signal returns 1 / 0 / None; aggregator sums non-None signals. Manufacturers use classic 5-factor Z; everyone else uses Z'' (no asset turnover). Real working capital and retained earnings — no proxies.
- **M5** — Earnings Quality module (`src/analysis/earnings_quality.py`): Beneish M-Score, Sloan accruals, Cash Conversion Ratio 5y avg. Combined into sector-relative `EarningsQuality_Score`.
- **M5** — Quality / Moat module (`src/analysis/quality_moat.py`): Gross Profitability (Novy-Marx), ROIC 5y avg + stability, operating margin stability, ROIC – WACC spread, reinvestment efficiency. Sector-relative `Moat_Score`.
- **M5** — Real Risk metrics (`src/analysis/risk_metrics.py`): realised 1y volatility, max drawdown 3y, ND/EBITDA, real interest coverage, 5y monthly Beta. Replaces the v1 Beta + InterestCoverage anaemic risk score with sector-relative `Risk_Score_v2`.
- **M6** — Two-stage DCF with sensitivity grid (`src/analysis/dcf.py`): WACC via CAPM, 5-year explicit FCF projection with revenue glide, Gordon-growth terminal, 3×3 WACC × TGR sensitivity. Outputs `DCF_FairValue_{Low,Mid,High}` and `DCF_MoS_{Low,Mid,High}`.
- **M6** — Activated MoS-driven signal logic in `generate_signal`: Strong Buy = composite ≥ 80 AND MoS ≥ 0.30 (price < 70% intrinsic). Strong Sell = MoS ≤ -0.30. Graceful fallback to legacy composite-only thresholds when DCF is NaN.
- **M7** — Three-horizon composite scoring (`src/analysis/horizon_scoring.py`): per-horizon weights and gates from `settings.yaml`. Outputs `score_lt`, `score_mt`, `score_st`, `signal_lt`, `signal_mt`, `signal_st`, `passes_gates_lt/mt/st`, `blockers_lt/mt/st`. Renormalised weighted mean drops NaN sub-scores from numerator and denominator. See [ADR-0001](docs/adr/0001-three-horizon-scoring.md).
- **M8** — Nine horizon presets (`src/strategy/horizon_presets.py`): `LT_QUALITY_COMPOUNDER`, `LT_PEA_DEFENSIVE`, `LT_DEEP_VALUE`, `MT_GARP`, `MT_TURNAROUND`, `MT_INCOME`, `ST_MOMENTUM_QUALITY`, `ST_EARNINGS_DRIFT`, `ST_OVERSOLD_BOUNCE`. Each extends a shared `_UNIVERSAL_PREFILTERS` block. Universal filters (`min_market_cap`, `min_avg_daily_volume_eur`, `min_years_listed`, `exclude_sectors`, `not_in_distress`, `min_data_completeness`) finally wired into `apply_filters`.
- **M9** — Momentum module (`src/analysis/momentum.py`): 12-1 momentum, RS_3m, MA crossings (50DMA, 200DMA, golden cross), volume surge.
- **M9** — EPS revisions module (`src/analysis/revisions.py`): 30d / 90d revision deltas, SUE z-score.
- **M9** — News sentiment module (`src/analysis/sentiment.py`): FinBERT (Hugging Face `ProsusAI/finbert`) over recent headlines. Optional dependency — gracefully skipped when `transformers` isn't installed.

**Data layer**

- **M2** — `MarketDataSource` Protocol (`backend/app/services/market_data/protocol.py`) with eight required `fetch_*` methods. Methods that a backend cannot supply must raise `NotImplementedError` so the orchestrator can distinguish "unsupported" from "missing".
- **M2** — `FMPDataFetcher` (`backend/app/services/market_data/fmp_fetcher.py`): Financial Modeling Prep free-tier client. Quota tracker (`data/cache/fmp_quota.json`), per-endpoint cache TTLs (24h fundamentals, 5min quotes, 1h news), kill-switch via `fmp.enabled`, daily-limit cap via `fmp.daily_limit`.
- **M2** — `YFinanceDataFetcher` (`backend/app/services/market_data/yfinance_fetcher.py`): yfinance fallback, used for prices/news/profile and FMP-missing fields.
- **M2** — `HybridDataFetcher` (`backend/app/services/market_data/hybrid_fetcher.py`): per-field fallback chain (FMP → yfinance → "missing"), `field_sources` audit trail, `data_completeness` per-row scalar. See [ADR-0002](docs/adr/0002-fmp-yfinance-hybrid.md).
- **M2** — Live coverage matrix (`backend/app/services/market_data/coverage_matrix.md`) generated from `field_sources` audits. Documents per-field FMP/yfinance availability and known gaps (.AS → .AMS mapping, GICS-vs-Yahoo sector taxonomy).

**Backend API**

- **M10** — Three-horizon Pydantic schema (`backend/app/models/horizons.py`, `company.py`, `screener.py`, `portfolio.py`, `watchlist.py`). New shared sub-models: `HorizonScoring`, `DCFValuation`, `QualitySignals`, `RiskSignals`, `MomentumSignals`, `SubScores`. Legacy `composite_score` / `signal` / `ScoringBreakdown` fields **removed**. See [ADR-0005](docs/adr/0005-atomic-frontend-backend-schema-replacement.md).
- **M10** — `tests/test_api_contract.py` pins the new schema as a regression target.
- **M10** — `openapi_v2.json` committed to repo root as a frozen reference.

**Frontend**

- **M11** — Three-horizon UI (`frontend/src/components/ui/`):
  - `HorizonSelector` — segmented LT/MT/ST control with `aria-selected`.
  - `HorizonScoreCard` — per-horizon score gauge + signal badge + gate state + blocker chips.
  - `DCFFairValueRange` — horizontal range bar (low/mid/high intrinsic vs price).
  - `MoSBar` — colour-coded margin-of-safety bar matching `generate_signal` thresholds.
  - `EarningsQualityPanel` — M-Score / Sloan / CCR with threshold annotations.
  - `MomentumPanel` — 12-1, RS_3m, MA crossings, volume surge, EPS revisions, SUE, sentiment.
  - `CTOWarningBanner` — banner for ST signals on PEA-eligible names.
- **M11** — Pages rewritten for v2 schema: `screener/page.tsx`, `company/[ticker]/`, `portfolio/`, `watchlist/`.
- **M11** — Hooks: `useCompany`, `useScreener`, `useHorizon` adapters.

**Backtesting**

- **M12** — Walk-forward backtest framework (`backend/app/services/backtest/walk_forward.py`):
  - Rebalance grid (monthly / quarterly / yearly).
  - Equal-weight basket capped at `max_position_size`.
  - Flat 10bp transaction cost per turnover.
  - Benchmark integration (CAC 40 / S&P 500 via `MarketDataSource.fetch_price_history`).
  - Per-preset alpha test against the relevant benchmark.
- **M12** — Metrics (`backend/app/services/backtest/metrics.py`): Sharpe, alpha/beta (OLS), max drawdown, hit rate, information ratio, CAGR, total return.
- **M12** — CLI entry point (`backend/app/services/backtest/cli.py`).
- **M12** — Sample backtest reports: `docs/backtests/LT_QUALITY_COMPOUNDER_2022-01-01_to_2024-12-31.md`, `docs/backtests/MT_TURNAROUND_2022-01-01_to_2024-12-31.md`.
- **M12** — Backtest methodology (`docs/backtests/methodology.md`): explicit acknowledgment of look-ahead bias, survivorship bias, transaction-cost model, cash-bucket convention, benchmark choice, statistical sample-size caveats.

### Changed

- **M10** — Public API schema replaced atomically (no v1 compatibility layer):
  - `composite_score` / `signal` / `scoring_breakdown` → `score_lt`, `score_mt`, `score_st`, `signal_lt`, `signal_mt`, `signal_st`, `sub_scores`, `valuation`, `quality`, `risk`, `momentum`.
  - All Pydantic models in `backend/app/models/` regenerated from the new shape.
  - **Breaking change**: any external consumer of v1 `/api/company/{ticker}` will fail until updated. Project has no external consumers; documented in [ADR-0005](docs/adr/0005-atomic-frontend-backend-schema-replacement.md).
- **M11** — Frontend rewritten to consume the M10 schema. Same atomic-cutover pattern; old shape no longer reachable from any page.
- **M3** — Legacy `_percentile_score` linear map replaced with sector-relative percentile rank in every M3+ sub-score generator.
- **M4** — Piotroski D/E inverted default fixed (NaN-safe comparison instead of `+inf` sentinel).
- **M4** — Piotroski signal #7 ("no dilution") now actually checks share count via `tk.get_shares_full()`. The unconditional "+1 by default" is gone.
- **M4** — Altman Z/Z'' uses real working capital (`CurrentAssets - CurrentLiabilities`) and real retained earnings from the balance sheet. The `Cash − 0.3 × Debt` and `0.4 × Equity` proxies are gone.
- **M5** — `Risk_Score_v2` (sector-relative, vol + drawdown + ND/EBITDA + real interest coverage + Altman Z + Beta) is now the input the M7 horizon scoring reads. Legacy `Risk_Score` (Beta + InterestCoverage only) stays in the DataFrame for snapshot-test compatibility but is no longer consumed by the composite.
- **M6** — `generate_signal` now activates the two-criterion path (composite + MoS) when DCF is computable. Legacy composite-only path becomes a graceful fallback when MoS is NaN.

### Fixed

7 critical bugs in scoring engine and data layer (audit §1, M1):

1. **EBIT aliased to EBITDA** — `data_fetcher.py:132,196` (v1) read `ebitda` and stored it as `EBIT`. Inflated ROIC by D&A / Invested Capital, distorted Altman X3, biased profitability scores upward for capital-intensive sectors. Fixed: real EBIT from `tk.financials` or FMP `operatingIncome`; NaN if both miss.

2. **Fabricated interest expense** — `data_fetcher.py:220` (v1) computed `interest_expense = totalDebt × 0.04`, a flat 4% rate over-estimating prime borrowers (Nestlé, ASML at 1–2%) and under-estimating distressed ones (8–12%). Fixed: pulled from income statement (`tk.financials.loc['Interest Expense']` or FMP `interestExpense`); NaN if missing.

3. **Piotroski D/E inverted default** — signal #4 (`CFO > NetIncome`) used `+inf` as the missing-NetIncome default, making the comparison always False. Fixed: NaN-aware comparison with explicit None handling.

4. **Piotroski signal #7 unconditional** — v1 awarded +1 by default for "no dilution" without checking actual share count. Every name got at least 1/9 free; score was inflated and signal-less on this dimension. Fixed: real share-count delta via `tk.get_shares_full()`; the helper returns `None` (not 1) when share history is unavailable.

5. **Altman Z fabricated WC and RE** — v1 computed `WC = Cash − 0.3 × TotalDebt` and `RE = 0.4 × Equity`. Fixed: pulls real `CurrentAssets`, `CurrentLiabilities`, `RetainedEarnings` from the balance sheet. Sector-aware dispatch picks Z (manufacturers) or Z'' (everyone else).

6. **`_percentile_score` linear map mislabelled as percentile** — function name implied a rank-based score, but implementation was a linear interpolation between hardcoded bounds. Penalised software, flattered utilities. Fixed: replaced with `score_sector_relative` (`src/analysis/sector_percentile.py`) using `df.groupby(Sector)[metric].rank(pct=True) * 100`. See [ADR-0003](docs/adr/0003-sector-relative-percentile.md).

7. **DCF documented but never implemented** — METHODOLOGY.md v1 devoted most space to DCF, the brief listed `dcf_model.py` and `valuation.py` in the architecture, and the signal logic depended on `Price < 70% of intrinsic value`. **No DCF code existed.** The "Strong Buy" gate could never trigger. Fixed (M6): two-stage DCF with sensitivity grid in `src/analysis/dcf.py`. The Strong Buy gate (composite ≥ 80 AND MoS ≥ 30%) now bites.

Plus two settings.yaml fields newly wired (audit §2.7):

8. **`min_avg_volume` / `min_avg_daily_volume_eur`** — declared in settings.yaml but never applied in `apply_filters()`. Small-caps with thin liquidity passed silently. Fixed: included in `_UNIVERSAL_PREFILTERS` (`src/strategy/horizon_presets.py`).

9. **`min_years_listed`** — declared in settings.yaml but never applied. Freshly-IPO'd names with 9-month history could pass screens that demand multi-year metrics. Fixed: included in `_UNIVERSAL_PREFILTERS`.

10. **`exclude_sectors`** (Tobacco, Gambling) — declared in settings.yaml but never applied. Fixed: included in `_UNIVERSAL_PREFILTERS`; `LT_PEA_DEFENSIVE` adds Energy_Producers as an ESG opt-in.

See [ADR-0004](docs/adr/0004-no-fabricated-values.md) for the full no-fabrication policy.

### Removed

- Legacy `composite_score`, `signal`, `scoring_breakdown` fields from API responses (M10).
- v1 frontend pages and components consuming the legacy shape (M11).
- The `_percentile_score(value, low, high)` linear map function in v1 `scoring_engine.py` (M3 — replaced, not deprecated).
- The `EBIT = EBITDA` alias and the `interest_expense = totalDebt × 0.04` fabrication (M1).
- The Piotroski "free point #7" (M4) and the Altman fictitious-input proxies (M4).

### Security

- **`.env` secrets discipline**: `.env.example` documents required variables; `.env` is gitignored; `FMP_TOKEN` loaded via `python-dotenv` in `backend/app/config.py`. No secrets committed.

### Known limitations (v0.4.0)

These are accepted gaps documented in the v2 docs, not bugs:

- **Backtest look-ahead bias**: M12's walk-forward backtest uses current-snapshot fundamentals as a proxy for historical inputs. Inflates apparent alpha for winners. Mitigation roadmap in `docs/backtests/methodology.md`.
- **Survivorship bias**: backtest universe is fixed at construction; delisted/acquired names absent from earlier rebalances.
- **FMP free-tier coverage gaps for European names**: Euronext (.PA, .AS) tickers often 404 on FMP statements; yfinance fallback covers most but not all. See `backend/app/services/market_data/coverage_matrix.md`.
- **Multi-period CAGRs not yet computed**: `growth_score_df` still uses TTM `RevenueGrowth` only; 5y CAGR over EPS / FCF / Revenue queued for M14.
- **Forward valuation columns**: `Forward_PE`, `EV_EBIT_Forward`, `Forward_PEG` are referenced by `MT_GARP` but not yet plumbed through `HybridDataFetcher`. `apply_filters` silently skips missing columns.
- **DCF for financials returns NaN**: banks/insurers don't have a meaningful FCF margin; DCF returns NaN with a warning. Use Graham Number + sector-relative P/B for these instead.
- **Sector taxonomy drift**: FMP uses GICS, yfinance uses Yahoo's taxonomy. Sector-relative scoring may drift on tickers where the two disagree.
- **WACC tax rate hardcoded at 25%**: Irish-domiciled (12.5%) and German (29.9%) names use the same assumption. Tracked for M14.

---

## [0.3.0] and earlier

Pre-v2 versions are not numbered formally. The git history retains the development log:

- `0.2.x` — initial Next.js frontend + FastAPI backend integration.
- `0.1.x` — pure-Python analysis engine; CLI-only.

The pre-v2 engine had the seven critical bugs documented above. Do not reach into the history expecting reliable numbers from it — see the audit (`AUDIT_2026-05-08_Screener_Metrics.md` in the project's research vault) for the full diagnosis.

---

## Links

- [METHODOLOGY.md](docs/METHODOLOGY.md) — v2 methodology
- [DATA_SOURCES.md](docs/DATA_SOURCES.md) — FMP + yfinance hybrid
- [PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — architecture
- [docs/adr/](docs/adr/) — architectural decision records
- [docs/backtests/methodology.md](docs/backtests/methodology.md) — backtest assumptions and biases
- [openapi_v2.json](openapi_v2.json) — frozen v2 OpenAPI spec
