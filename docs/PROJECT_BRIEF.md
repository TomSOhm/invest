# Invest Solo — Project Brief (v2)

**Owner:** Tom S (`Ohm-T`).
**Status:** v2 release (M0–M12 complete; M13 documents the engine).
**Last updated:** 2026-05-08.

This brief is the architectural map. For methodology details see [`METHODOLOGY.md`](METHODOLOGY.md); for data layer detail see [`DATA_SOURCES.md`](DATA_SOURCES.md); for the design rationale of structural choices see [`adr/`](adr/).

---

## 1. Mission

A quantitative fundamental investment platform for a French investor running both a **PEA** (Plan d'Épargne en Actions, EU/EEA-only, tax-advantaged) and a **CTO** (compte-titres ordinaire, unconstrained). The engine evaluates stocks on three independent horizons (long, medium, short) and surfaces buy/sell signals with the data provenance and DCF margin of safety needed to act with confidence.

v2 (M0–M12) rebuilt every component identified as broken or missing in the 2026-05-08 audit. v1's single composite, fabricated EBIT, and absent DCF are gone; the engine now uses sector-relative percentile ranks, real Piotroski deltas, real Altman Z'' inputs, and a two-stage DCF with a 3×3 sensitivity grid.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES (M2)                               │
│                                                                          │
│   FMP (250 calls/day, US-strong)  ←─┐                                    │
│                                      │  HybridDataFetcher                │
│   yfinance (free, EU-strong)     ←─┴─→ per-field fallback chain          │
│                                                                          │
│   Cache: data/cache/ (24h fundamentals, 1h news, 5min quotes)            │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────────────┐
│                       SCORING ENGINE (src/analysis)                      │
│                                                                          │
│   M3  sector-relative percentiles → Valuation/Profitability/Health/...   │
│   M4  real Piotroski + Altman Z''                                        │
│   M5  EarningsQuality, Moat, Risk_Score_v2                               │
│   M6  two-stage DCF + sensitivity grid                                   │
│   M7  three-horizon composites (LT/MT/ST) + gates                        │
│   M9  momentum + EPS revisions + FinBERT sentiment                       │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────────────┐
│                    SCREENER + STRATEGY (src/strategy)                    │
│                                                                          │
│   apply_filters() — universal pre-filters + horizon gates                │
│   PRESET_REGISTRY (M8) — 9 named presets across 3 horizons               │
│   screen_horizon_preset() — apply preset, sort by horizon score          │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────────────┐
│                      BACKEND API (backend/app)                           │
│                                                                          │
│   FastAPI + Pydantic v2; M10 atomically replaced legacy schema           │
│   Routes: /api/company, /api/screener, /api/portfolio, /api/watchlist    │
│   Backtest: /api/backtest (M12, walk-forward against benchmark)          │
│   Storage: JSON files (data/portfolio.json, data/watchlist.json)         │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────────────┐
│                     FRONTEND (frontend/, Next.js 16)                     │
│                                                                          │
│   Pages: dashboard, screener, company/[ticker], portfolio, watchlist     │
│   M11 components: HorizonSelector, DCFFairValueRange, MoSBar,            │
│                  EarningsQualityPanel, MomentumPanel, CTOWarningBanner   │
└─────────────────────────────────────────────────────────────────────────┘
```

Two key structural patterns:

- **`MarketDataSource` Protocol** (`backend/app/services/market_data/protocol.py`) — every backend (FMP, yfinance, future EODHD) implements the same eight `fetch_*` methods. The hybrid composer doesn't know or care which backend produced a given field.
- **Pure-function scoring modules** — every `src/analysis/` module is I/O-free. Inputs are DataFrames the data layer already filled in; outputs are columns or per-ticker scalars. Easy to unit-test, easy to backtest, easy to reason about.

---

## 3. Three-horizon scoring (M7)

Every ticker gets three independent composites and gate states:

| Output column | Long-Term | Medium-Term | Short-Term |
|---|---|---|---|
| `score_lt` / `score_mt` / `score_st` | composite 0–100 | composite 0–100 | composite 0–100 |
| `signal_lt` / `signal_mt` / `signal_st` | Strong Buy / Buy / Hold / Sell / Strong Sell | (same set) | (same set) |
| `passes_gates_lt` / `_mt` / `_st` | bool — every gate satisfied | bool | bool |
| `blockers_lt` / `_mt` / `_st` | list of failing gate keys | list | list |
| `recommended_account` | (none) | (none) | "CTO" when ST passes (PEA caveat) |

Per-horizon weights and gates live in `settings.yaml` `horizons:` block; `src/analysis/horizon_scoring.py` consumes them directly. The audit's "single signal regardless of horizon" critique drove this split — see [ADR-0001](adr/0001-three-horizon-scoring.md).

---

## 4. The 9 horizon presets (M8)

`src/strategy/horizon_presets.py` registers 9 named filter dicts, one per (horizon × style) combination. Each extends a shared `_UNIVERSAL_PREFILTERS` block.

### Long-Term (5y+)

- **`LT_QUALITY_COMPOUNDER`** — Default LT preset. Buy great businesses at fair prices and hold for compounding. Combines a ROIC ≥ 12% floor, Piotroski ≥ 7 (real, not proxy), Altman Z'' ≥ 2.6, ND/EBITDA ≤ 2.5, sector-relative valuation cap, DCF MoS ≥ 15%, multi-period revenue and EPS CAGRs. Tax-optimal in PEA.
- **`LT_PEA_DEFENSIVE`** — PEA-strict, lower-volatility tilt. Adds Beta ≤ 1.0, Div Yield ≥ 2%, payout ≤ 65%, market cap ≥ €1B, ESG sector exclusions including Energy_Producers. Designed for the income-leaning core of a PEA.
- **`LT_DEEP_VALUE`** — Contrarian. Targets the cheapest sector tier (P/B ≤ 1.5, EV/EBIT ≤ 9, DCF MoS ≥ 30%) but layers anti-value-trap gates on top: Piotroski ≥ 6, Altman Z ≥ 1.8, ROIC 5y avg ≥ 6%, positive FCF in ≥ 3 of last 5 years.

### Medium-Term (1–3y)

- **`MT_GARP`** — Growth at reasonable price. Forward P/E ≤ 18, PEG ≤ 1.3, EPS revisions positive over 6m, op margin trend +50bp/y, price > 200dma, 3m relative strength positive. Looks for re-rating catalysts within a 1–3y window. Holding period straddles PEA's 5y threshold; preferred-account is PEA when holding through.
- **`MT_TURNAROUND`** — Higher-risk operational improvement. Target companies that were bad and are getting better: op margin improvement ≥ 300bp YoY, FCF positive latest year, Altman Z ≥ 1.5. Recommended max position size 3% of portfolio.
- **`MT_INCOME`** — Dividend-focused. Yield ≥ 3.5%, payout ≤ 75%, 5y dividend growth ≥ 3%, FCF coverage of dividends ≥ 1.4×, ≥ 10 consecutive dividend years. Suited for the PEA dividend-compounder bucket.

### Short-Term (<6mo)

All ST presets carry `recommended_account: "CTO"` and `pea_warning: True`.

- **`ST_MOMENTUM_QUALITY`** — Quantitative momentum + quality floor. 12-1 momentum top quartile, golden cross, volume surge ≥ 1.3, SUE ≥ 1, max realised vol 50%. Quality floor (Altman Z ≥ 1.5, Piotroski ≥ 5) prevents chasing pump-and-dump names.
- **`ST_EARNINGS_DRIFT`** — Post-Earnings Announcement Drift. Trigger: earnings within 5 days, SUE ≥ 1.5, volume surge ≥ 2.0, gap up ≥ 3%. Hold 30–60 days. Exit on 50dma break, negative relative strength, or new negative news.
- **`ST_OVERSOLD_BOUNCE`** — Mean reversion. Connors RSI(2) < 10 in a long-term uptrend (price > 200dma), no recent negative news, no earnings within 3 days. Hold 3–10 days, target 50dma, stop loss 1 ATR below entry.

Each preset is documented inline in the source file. Sample backtest output for two presets is committed at:
- `docs/backtests/LT_QUALITY_COMPOUNDER_2022-01-01_to_2024-12-31.md`
- `docs/backtests/MT_TURNAROUND_2022-01-01_to_2024-12-31.md`

Read those alongside [`docs/backtests/methodology.md`](backtests/methodology.md) for assumptions and known biases.

---

## 5. Folder layout

```
invest/
├── backend/                         # FastAPI REST API
│   └── app/
│       ├── api/                     # Route handlers (company, market, screener, portfolio, watchlist)
│       ├── models/                  # Pydantic models (M10 schema)
│       │   ├── company.py           # CompanyDetail (three-horizon)
│       │   ├── horizons.py          # HorizonScoring, DCFValuation, QualitySignals,
│       │   │                        # RiskSignals, MomentumSignals, SubScores
│       │   ├── screener.py          # ScreenerRequest/Response (horizon-aware)
│       │   └── portfolio.py, watchlist.py
│       ├── services/                # Business logic
│       │   ├── data_fetcher.py      # Thin facade — delegates to HybridDataFetcher
│       │   ├── market_data/         # M2 data layer
│       │   │   ├── protocol.py             # MarketDataSource Protocol
│       │   │   ├── fmp_fetcher.py          # FMP backend
│       │   │   ├── yfinance_fetcher.py     # yfinance backend
│       │   │   ├── hybrid_fetcher.py       # Orchestrator
│       │   │   └── coverage_matrix.md      # Live FMP/yfinance coverage
│       │   ├── scoring_service.py   # Wraps src/analysis/scoring_engine
│       │   ├── screener_service.py  # Wraps src/strategy/screener
│       │   ├── company_service.py   # Builds CompanyDetail from raw row + scores
│       │   ├── portfolio_service.py # JSON-backed portfolio CRUD
│       │   ├── watchlist_service.py # JSON-backed watchlist CRUD
│       │   ├── cache_service.py     # File-based JSON cache
│       │   ├── config_service.py    # Loads settings.yaml
│       │   └── backtest/            # M12 backtest framework
│       │       ├── walk_forward.py  # WalkForwardBacktester
│       │       ├── metrics.py       # Sharpe, alpha/beta, drawdown, hit rate, IR
│       │       └── cli.py           # Command-line entry point
│       ├── storage/                 # JSON persistence helpers
│       ├── config.py                # Settings, sys.path bootstrap
│       ├── dependencies.py          # FastAPI dependency injection
│       └── main.py                  # FastAPI app factory
│
├── frontend/                        # Next.js 16 + React 19 + Tailwind 4
│   └── src/
│       ├── app/                     # App Router pages
│       │   ├── page.tsx             # Dashboard
│       │   ├── screener/page.tsx
│       │   ├── company/[ticker]/    # Company detail page
│       │   ├── portfolio/
│       │   └── watchlist/
│       ├── components/
│       │   ├── ui/                  # M11 visual primitives
│       │   │   ├── HorizonSelector.tsx       # LT / MT / ST segmented control
│       │   │   ├── HorizonScoreCard.tsx       # Per-horizon score + signal + gate state
│       │   │   ├── DCFFairValueRange.tsx      # Low/mid/high range bar
│       │   │   ├── MoSBar.tsx                 # Margin-of-safety progress bar
│       │   │   ├── EarningsQualityPanel.tsx   # M-Score / Sloan / CCR
│       │   │   ├── MomentumPanel.tsx          # 12-1, RS_3m, MAs, volume, sentiment
│       │   │   ├── CTOWarningBanner.tsx       # PEA-caveat banner for ST signals
│       │   │   ├── PeaBadge.tsx, SignalBadge.tsx, ScoreGauge.tsx
│       │   │   └── Card.tsx, Modal.tsx, Spinner.tsx, MetricCard.tsx, Badge.tsx
│       │   └── layout/                        # Header, Footer, Sidebar
│       ├── hooks/                             # useCompany, useScreener, useHorizon
│       └── lib/                               # api.ts, types.ts, formatters.ts
│
├── src/                             # Pure-function analysis engine
│   ├── analysis/
│   │   ├── scoring_engine.py        # Orchestrator: M3 sub-scores + composite
│   │   ├── sector_percentile.py     # M3 sector-relative percentile rank
│   │   ├── quality_signals.py       # M4 real Piotroski + Altman Z/Z''
│   │   ├── earnings_quality.py      # M5 Beneish, Sloan, CCR
│   │   ├── quality_moat.py          # M5 GP/TA, ROIC stability, moat
│   │   ├── risk_metrics.py          # M5 vol, drawdown, real risk
│   │   ├── dcf.py                   # M6 two-stage DCF + sensitivity
│   │   ├── horizon_scoring.py       # M7 three-horizon composites
│   │   ├── momentum.py              # M9 12-1, MAs, volume surge
│   │   ├── revisions.py             # M9 EPS revisions, SUE
│   │   └── sentiment.py             # M9 FinBERT (optional)
│   ├── strategy/
│   │   ├── screener.py              # apply_filters + filter helpers
│   │   └── horizon_presets.py       # M8 PRESET_REGISTRY (9 presets)
│   ├── data/
│   │   ├── sample_universe.py       # 31 PEA-eligible companies sample
│   │   └── (raw CSVs)
│   ├── reporting/                   # Charts, dashboards, exports
│   ├── portfolio/                   # Tracker, allocation, rebalancer (legacy)
│   ├── main.py                      # Standalone screener entry point
│   └── daily_run.py                 # Daily analysis pipeline
│
├── tests/                           # 400+ pytest tests
│   ├── test_scoring_engine_vectorised.py
│   ├── test_scoring_snapshot.py     # M0 golden-file regression harness
│   ├── test_sector_percentile.py
│   ├── test_quality_signals.py
│   ├── test_earnings_quality.py
│   ├── test_quality_moat.py
│   ├── test_risk_metrics.py
│   ├── test_dcf.py
│   ├── test_horizon_scoring.py
│   ├── test_horizon_presets.py
│   ├── test_momentum.py, test_revisions.py, test_sentiment.py
│   ├── test_hybrid_fetcher.py, test_yfinance_fetcher.py
│   ├── test_api_contract.py         # Pydantic schema regression
│   ├── backtest/                    # Backtest framework tests
│   ├── golden/                      # Snapshot data
│   └── conftest.py
│
├── scripts/
│   ├── capture_golden_snapshots.py  # Regenerate golden snapshots
│   ├── coverage_report.py           # Populate coverage_matrix.md per ticker
│   └── m5_score_golden.py
│
├── docs/
│   ├── PROJECT_BRIEF.md             # This file
│   ├── METHODOLOGY.md               # v2 methodology
│   ├── DATA_SOURCES.md              # FMP+yfinance hybrid
│   ├── PEA_RULES.md                 # PEA eligibility + tax (unchanged)
│   ├── PYTHON_FUNCTIONS.md          # Function-by-function reference
│   ├── adr/                         # Architectural Decision Records (v2)
│   ├── backtests/                   # Backtest methodology + sample outputs
│   └── assets/                      # Banner SVGs
│
├── data/                            # Local storage (gitignored except samples)
│   ├── cache/                       # JSON cache (fundamentals, prices, quota)
│   ├── exports/                     # Generated reports
│   ├── portfolio.json               # User portfolio
│   └── watchlist.json               # User watchlist
│
├── settings.yaml                    # All config: weights, thresholds, horizons, screener, FMP
├── openapi_v2.json                  # OpenAPI spec for the v2 API
├── pyproject.toml
├── Makefile                         # Common commands (backend, frontend, tests)
├── README.md
├── CHANGELOG.md                     # Milestone-by-milestone (M0–M12)
├── CONTRIBUTING.md
├── LICENSE                          # Apache 2.0
└── .env.example                     # API key template
```

---

## 6. Frontend pages and key components (M11)

### Pages

- **`/` (dashboard)** — Universe summary: signal distribution per horizon, top picks per preset, FMP quota status.
- **`/screener`** — Horizon selector + preset dropdown + custom-filter form. Renders results sorted by `score_<horizon>`. Shows blockers per row.
- **`/company/[ticker]`** — Full CompanyDetail view. Hero shows three-horizon scores side-by-side; below: DCF range bar, sub-score gauges, earnings quality panel, momentum panel, raw metrics table.
- **`/portfolio`** — Holdings table, P&L, weights, sector concentration, drift alerts.
- **`/watchlist`** — Tickers tagged with notes; sortable by any horizon score.

### Key components (`frontend/src/components/ui/`)

- **`HorizonSelector`** — Segmented control (LT / MT / ST) with `aria-selected` for accessibility. Drives the `useHorizon()` hook that filters every horizon-aware view.
- **`HorizonScoreCard`** — Card showing one horizon's score (gauge), signal (badge), pass/fail gates, and blocker chips when failing.
- **`DCFFairValueRange`** — Horizontal range bar showing low/mid/high intrinsic values relative to current price; price marker on top. Surfaces `wacc_used` and warnings.
- **`MoSBar`** — Single-axis bar rendering MoS as a percentage; colour-coded against the `generate_signal` thresholds (≥ 30% green, 15–30% light green, ±15% grey, ≤ -15% red, ≤ -30% deep red).
- **`EarningsQualityPanel`** — M-Score, Sloan accruals, CCR_5y in a compact grid with threshold chips ("aggressive accruals", "potential manipulator").
- **`MomentumPanel`** — 12-1 momentum, RS_3m, MA crossings, volume surge, EPS revisions, SUE, sentiment. Used on company detail page; collapses on screener page.
- **`CTOWarningBanner`** — Red banner that renders whenever a PEA-eligible name has a passing ST signal. Explains the PEA tax-wrapper risk for short-term trading.
- **`PeaBadge`**, **`SignalBadge`**, **`ScoreGauge`** — primitives reused across pages.

API proxy: `frontend/next.config.ts` rewrites `/api/*` to `http://localhost:8000/api/*` so the frontend runs against a local backend without CORS gymnastics.

---

## 7. Backtest framework (M12)

`backend/app/services/backtest/walk_forward.py`. Walk-forward rebalanced portfolios applied to the 9 horizon presets, validated against an appropriate benchmark (CAC 40 for PEA presets, S&P 500 for global).

### Mechanics

1. At each rebalance date (default = quarter-end), score the universe via `score_dataframe`.
2. Apply the named preset's filters via `screen_horizon_preset`.
3. Equal-weight the surviving names; cap at `max_position_size` (default 10% → max 10 names).
4. Hold until next rebalance.
5. Debit a flat 10bp transaction cost per rebalance turnover.

### Acknowledged biases (v0)

- **Look-ahead bias** — current-snapshot fundamentals proxy historical inputs; mitigation in `docs/backtests/methodology.md` is point-in-time fundamentals at M14+.
- **Survivorship bias** — fixed universe at construction; delisted/acquired names absent from earlier rebalances.
- **Transaction cost** — flat 10bp; understates costs for micro-cap-heavy presets.
- **Cash bucket** — earns 0% (conservative when rates were low; generous when rates were high).
- **Benchmark** — price-only (no dividends reinvested). Slightly biased against high-yielding strategies.
- **Statistical sample size** — 5 years × quarterly rebalance = ~20 observations. Reported alphas are descriptive, not inferential.

Full discussion in [`docs/backtests/methodology.md`](backtests/methodology.md).

CLI: `python -m backend.app.services.backtest.cli --preset LT_QUALITY_COMPOUNDER --start 2022-01-01 --end 2024-12-31`.

---

## 8. PEA-specific rules (unchanged from v1)

- Company **headquartered in EU/EEA**: see `pea.eligible_countries` in `settings.yaml` (FR, DE, NL, BE, IT, ES, PT, IE, AT, FI, SE, DK, NO, PL, LU, GR).
- Listed on European exchanges (Euronext, Frankfurt, Milan, etc.).
- ETFs eligible if composed of ≥ 75% eligible equities.
- REITs (SIICs) excluded since 2012.
- **Long-only, no leverage, no shorts.**
- **5y tax lock-in** — withdrawals before 5 years close the account and trigger PFU (30%). After 5y, 17.2% social charges only on gains.
- **PEA-PME**: official criterion is < 5,000 employees AND (Revenue < €1.5B OR Total Assets < €2B). v1 used a market-cap proxy that was wrong; v2 still uses the proxy until FMP's profile endpoint exposes employees + revenue + assets reliably (tracked).

Full discussion in [`docs/PEA_RULES.md`](PEA_RULES.md).

---

## 9. Architectural Decision Records

The structural choices in v2 are documented in `docs/adr/`. Each ADR is dated, has a status, and links the audit + implementation files that justified the decision.

| ADR | Title | Status |
|---|---|---|
| [0001](adr/0001-three-horizon-scoring.md) | Three-horizon scoring (replaces single composite) | Accepted (M7) |
| [0002](adr/0002-fmp-yfinance-hybrid.md) | FMP + yfinance hybrid via Protocol pattern | Accepted (M2) |
| [0003](adr/0003-sector-relative-percentile.md) | Sector-relative percentile rank (replaces linear map) | Accepted (M3) |
| [0004](adr/0004-no-fabricated-values.md) | NaN over fabricated proxies (no 4% interest, no 30% WC) | Accepted (M1) |
| [0005](adr/0005-atomic-frontend-backend-schema-replacement.md) | Atomic v1→v2 schema replacement (M10+M11 ship together) | Accepted (M10/M11) |

---

## 10. Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, pandas, numpy, loguru |
| Data | yfinance, Financial Modeling Prep (free tier), httpx (or requests fallback) |
| Analysis | Pure pandas/numpy. No FinanceToolkit dependency in the scoring path. FinBERT (transformers) optional for sentiment. |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Recharts, lucide-react |
| Storage | JSON files for portfolio/watchlist (V1); cache via JSON-on-disk |
| Tooling | bun (frontend package mgr), pytest (~400 tests), Make (`make backend`, `make frontend`, `make test`) |

---

## 11. Quick start

### Prerequisites

- Python 3.11+ (3.10 works but untested in CI).
- Node 18+ and `bun` (`npm install -g bun`).
- Optional: an FMP free-tier key at `https://financialmodelingprep.com/developer`.

### Setup

```bash
git clone https://github.com/TomSOhm/invest.git
cd invest

# API keys (optional — yfinance works without keys)
cp .env.example .env
# edit .env: set FMP_TOKEN if you have one

# Python deps
pip install -e backend

# Frontend deps
cd frontend && bun install && cd ..
```

### Run

```bash
# Backend on :8000
make backend          # python -m uvicorn backend.app.main:app --reload

# Frontend on :3000 (separate terminal)
make frontend         # cd frontend && bun run dev

# Standalone screener (CLI)
python src/main.py

# Run tests
make test             # pytest
```

Open `http://localhost:3000` for the dashboard, `http://localhost:8000/docs` for the OpenAPI explorer.

---

## 12. References

- v2 documentation:
  - [`METHODOLOGY.md`](METHODOLOGY.md) — three-horizon methodology, sub-scores, DCF, gates.
  - [`DATA_SOURCES.md`](DATA_SOURCES.md) — FMP + yfinance hybrid, coverage matrix.
  - [`PEA_RULES.md`](PEA_RULES.md) — PEA eligibility and tax rules.
  - [`adr/`](adr/) — ADRs 0001–0005.
  - [`backtests/methodology.md`](backtests/methodology.md) — backtest assumptions and biases.
- v2 entry points:
  - [`CHANGELOG.md`](../CHANGELOG.md) — milestone-by-milestone (M0–M12).
  - [`openapi_v2.json`](../openapi_v2.json) — full API surface.
  - [`README.md`](../README.md) — top-level overview.
