# Data Sources — FMP + yfinance Hybrid

**Status:** Active (v2 data layer; M2 milestone).
**Last updated:** 2026-05-08.
**Companion docs:** [`METHODOLOGY.md`](METHODOLOGY.md), [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md), [`adr/0002-fmp-yfinance-hybrid.md`](adr/0002-fmp-yfinance-hybrid.md), [`backend/app/services/market_data/coverage_matrix.md`](../backend/app/services/market_data/coverage_matrix.md) (live coverage).

---

## 0. TL;DR

The engine fetches fundamentals from **Financial Modeling Prep (FMP)** when available and falls back to **yfinance** per-field when FMP returns no data (404, quota exceeded, missing endpoint). The orchestrator is `HybridDataFetcher` (`backend/app/services/market_data/hybrid_fetcher.py`); both backends implement the `MarketDataSource` Protocol (`backend/app/services/market_data/protocol.py`) so swapping in EODHD or Finnhub later is a one-class change. Each value carries a `field_sources` audit trail so `data_completeness` can be computed honestly per ticker.

The v1 layer (yfinance only, with proxies for missing fields) is gone. v1's fabricated EBIT, fabricated interest expense, and 4%-flat-rate cost of debt are documented in [ADR-0004](adr/0004-no-fabricated-values.md) — replaced with NaN where the source has no data.

---

## 1. Why the hybrid

yfinance is reliable for prices, market cap, basic info, and price history — its weaknesses are in the income statement and balance sheet detail (EBIT, retained earnings, current assets, working capital, EPS revisions). FMP's free tier exposes those statements directly but is rate-limited (250 calls/day) and US-strong / EU-sparse.

Combining the two:

- **FMP-first** for fundamentals (income, balance, cash flow, ratios).
- **yfinance fallback** when FMP misses (EU tickers commonly 404 the statements endpoints) or when the daily quota is exhausted.
- **yfinance-only** for prices, news, profile, EPS (when FMP doesn't cover it on the free tier).

The decision tree and trade-offs are spelled out in [ADR-0002](adr/0002-fmp-yfinance-hybrid.md).

---

## 2. FMP — primary fundamentals source

**API:** `https://financialmodelingprep.com/api/v3/`
**Auth:** API key passed as `?apikey=...` query param. Loaded from `FMP_TOKEN` env var (see `.env.example`).
**Free tier:** 250 calls/day, **5 years of history**, US universe full, EU universe partial.
**Implementation:** `backend/app/services/market_data/fmp_fetcher.py`.

### Endpoints used

| Endpoint | Purpose | Cache TTL |
|---|---|---|
| `/income-statement/{ticker}?period=annual&limit=5` | Revenue, EBIT, EBITDA, NetIncome, GrossMargin, OpMargin, NetMargin, InterestExpense, COGS, SGA, D&A | 24h |
| `/balance-sheet-statement/{ticker}?period=annual&limit=5` | TotalAssets, TotalEquity, TotalDebt, Cash, CurrentAssets, CurrentLiabilities, RetainedEarnings, LongTermDebt, Receivables, PPE | 24h |
| `/cash-flow-statement/{ticker}?period=annual&limit=5` | OperatingCashflow, FCF, CapEx | 24h |
| `/key-metrics/{ticker}?period=annual&limit=5` | ROE, ROA, ROIC, payoutRatio | 24h |
| `/ratios/{ticker}?period=annual&limit=5` | ratio shortcuts (used for fallback when key-metrics is sparse) | 24h |
| `/quote/{ticker}` | Price, MarketCap, EV, Shares, Beta, AvgVolume, 52w high/low | 5 min |
| `/profile/{ticker}` | Name, Sector, Industry, Country, Exchange, FirstTradeDate | 24h |
| `/historical-price-full/{ticker}?serietype=line` | OHLCV history (used by momentum, vol, drawdown) | 24h |
| `/analyst-estimates/{ticker}` | Forward EPS revisions, target prices | 6h |
| `/stock_news?tickers={ticker}&limit=20` | News headlines (feeds FinBERT sentiment) | 1h |

**Quarterly statements** (`?period=quarter`) are also fetched when the M9 SUE / earnings-revision logic needs them; cached at 6h.

### Quota tracker

`data/cache/fmp_quota.json` persists `{ "date": "YYYY-MM-DD", "count": N }`. Counter resets at midnight UTC. When `count >= settings.fmp_daily_limit` (default 240, hardcoded conservative cap below the 250 free-tier limit), `FMPDataFetcher` raises `FMPQuotaExceeded` and `HybridDataFetcher` falls through to yfinance for the rest of the day.

The kill-switch `fmp.enabled: false` in `settings.yaml` bypasses FMP entirely — useful for offline development and CI runs.

### Ticker symbol mapping

yfinance uses `.PA`, `.AS`, `.DE`, `.SW`, `.L` suffixes; FMP free tier understands some but not all. `_to_fmp_symbol()` in `fmp_fetcher.py` handles the mapping (e.g. `.AS` → `.AMS`, partial reliability per the coverage matrix).

### Errors / fallthrough

| HTTP | Behaviour |
|---|---|
| 200 | Parse JSON; cache; return. |
| 401 | Bad token → raise `FMPHTTPError(401)`. Hybrid bubbles up — kill-switch FMP. |
| 403 | Quota or forbidden → raise `FMPHTTPError(403)`. Hybrid falls through to yfinance. |
| 404 | Ticker / endpoint not covered → raise `FMPHTTPError(404)`. Hybrid falls through. |
| 429 | Rate-limit → raise `FMPHTTPError(429)`. Hybrid falls through. |
| 5xx | Transient → raise `FMPHTTPError(5xx)`. Hybrid falls through. |
| `FMPQuotaExceeded` | Raised before the call when `count >= daily_limit`. Hybrid falls through immediately. |

### Rate-limit budget

Worst case for a 200-ticker daily refresh:

- 9 endpoints × 200 tickers = 1,800 calls.
- Free tier hard cap: 240 calls/day (settings buffer below 250).
- **Therefore 24h cache on fundamentals is mandatory**. Without it, a single full-universe refresh exhausts a week's quota.

In practice, most days fetch ~20–50 calls (price refreshes hit the 5min cache; fundamentals served from the 24h cache). The 240 limit accommodates ~25 new tickers/day or one full mid-cap PEA-eligible refresh per quarter.

---

## 3. yfinance — fallback + price source

**Library:** `pip install yfinance`.
**Auth:** none (unofficial Yahoo Finance scraper).
**Coverage:** global; Euronext suffixes (`.PA`, `.AS`, `.BR`, `.LS`), Frankfurt (`.DE`), Milan (`.MI`), Oslo (`.OL`), London (`.L`).
**Implementation:** `backend/app/services/market_data/yfinance_fetcher.py`.

### What yfinance is used for

1. **Prices, OHLCV history, market cap, beta** — primary source (FMP quote also has these but yfinance is more reliable for EU names).
2. **Per-field fundamentals fallback** — when FMP 404s on EU tickers, yfinance fills in `Revenue`, `EBIT`, `TotalAssets`, etc. via `tk.financials`, `tk.balance_sheet`, `tk.cashflow`.
3. **News** — `tk.news` (used by `FinBERT` for sentiment when FMP news is missing).
4. **Profile** — `tk.info["sector"]`, `tk.info["country"]`, `tk.info["firstTradeDateEpochUtc"]`. Note: yfinance returns sector under Yahoo's taxonomy, FMP uses GICS — see [§7 known gaps](#7-known-gaps).
5. **Share count history** — `tk.get_shares_full()` is the only way to compute year-over-year dilution for Piotroski signal #7. FMP doesn't expose share-count timeseries on the free tier.

### Reliability notes

- yfinance can break silently when Yahoo changes its scraping target. Behaviour is graceful: the fetcher returns NaN, source = "missing", and `data_completeness` drops.
- Some `.info` fields (`pegRatio`, `targetMeanPrice`, `forwardEps`) are stale or missing for non-US tickers. The hybrid prefers FMP for these when available.
- yfinance's `debtToEquity` is returned as percentage (e.g. 45 = 0.45) — `_safe_div` and the data fetcher's normaliser handle the unit conversion.
- No rate limit on the free yfinance API at the project's scale (~tens of tickers/day with caching); the throttling concern is Yahoo's anti-scraping rather than a documented quota.

---

## 4. HybridDataFetcher — orchestration

`backend/app/services/market_data/hybrid_fetcher.py`. Combines FMP and yfinance behind the `MarketDataSource` Protocol.

### Per-field fallback chain

For each scoring field:

1. Try FMP. If a finite numeric is returned → record it with `source="fmp"`.
2. On `FMPQuotaExceeded` / `FMPHTTPError` / `NotImplementedError` / NaN-back, try yfinance. If yfinance produces a finite numeric → `source="yfinance"`.
3. On both failing → `source="missing"`, value = NaN.

### `field_sources` audit trail

Every fetched row carries a parallel dict mapping every field to its provenance:

```python
row = {
    "Revenue": 271_810_000_000,  # value
    "EBIT": 89_500_000_000,
    "InterestExpense": float("nan"),
    ...
}
field_sources = {
    "Revenue": "fmp",
    "EBIT": "fmp",
    "InterestExpense": "missing",
    ...
}
```

`data_completeness` is then `sum(s != "missing") / len(field_sources)`. The horizon gates use this directly (`min_data_completeness`).

### Cache strategy

| Class | TTL | Why |
|---|---|---|
| Annual fundamentals | 24h | Statements only update on earnings (quarterly at most); 24h amortises across the universe. |
| Quarterly fundamentals | 6h | Earnings-day refreshes need to be picked up same day. |
| Quotes / prices | 5 min | Intraday display; price changes rapidly during market hours. |
| Price history (OHLCV) | 24h | Used for momentum / vol; daily granularity is enough. |
| News | 1h | Sentiment freshness for ST signals. |
| Analyst estimates | 6h | Revisions arrive throughout the trading day. |
| FMP quota | persistent (date-keyed) | One quota bucket per UTC day. |

Cache is JSON-on-disk under `data/cache/` with the `CacheService` wrapper (`backend/app/services/cache_service.py`). Keys use `fmp:{endpoint_tag}:{original_ticker}` (original, not FMP-mapped, so cache invalidation stays consistent across symbol-mapping fixes).

---

## 5. Coverage matrix highlights

The full live matrix is in [`backend/app/services/market_data/coverage_matrix.md`](../backend/app/services/market_data/coverage_matrix.md). Key takeaways:

| Ticker class | FMP coverage | yfinance fill-in needed | DCF computable? |
|---|---|---|---|
| US large-cap (AAPL, MSFT, NVDA) | Full income/balance/cashflow + quote + profile | Rare (Beta, news only) | Yes |
| EU large-cap (ASML.AS, MC.PA, SAP.DE) | Mixed: income statements often present, balance sheets sometimes 404, ratios partial | Common (TotalEquity, EBIT for some) | Yes for most |
| EU mid-cap (HEIA.AS, AIR.PA) | Sparse: profile + quote yes, statements often 404 | Heavy (Revenue, EBIT, TotalAssets via yfinance) | Sometimes |
| Financials (BNP.PA, JPM, BRK-B) | Statements present | — | **No** — FCF margin undefined for banks/insurers; DCF returns NaN with warning |
| Hermès, LVMH | Mixed; ratios partial | Common | Yes |
| Sanofi (SAN.PA) | Mixed; statements partial | Common | Sometimes (FCF margin sometimes NaN) |

**Specific data-completeness observations** (from M5 coverage runs):

- Apple (AAPL) — full FMP coverage; `data_completeness` typically 0.95+.
- Hermès (RMS.PA) — mixed; some balance-sheet fields fall to yfinance; `data_completeness` typically 0.75–0.85.
- Sanofi (SAN.PA) — similar mixed pattern; FCF margin sometimes NaN, leading the DCF to return NaN.
- BNP Paribas (BNP.PA) — financials lack a meaningful FCF margin; DCF returns NaN with `"Non-positive FCF margin"` warning. The horizon scores still compute via Valuation_Score (sector-relative P/B is meaningful for banks) and Health_Score (Altman Z'' applies).

The coverage matrix file ends with a placeholder for live per-ticker reports populated by `scripts/coverage_report.py`.

---

## 6. Other data signals

### News + sentiment (M9)

- Headlines: FMP `/stock_news` first; yfinance `tk.news` fallback.
- Sentiment: FinBERT (Hugging Face `ProsusAI/finbert`) via `src/analysis/sentiment.py`. Optional dependency — when `transformers` is not installed, sentiment is silently skipped (test `tests/test_sentiment.py` is marked `pytest.skip` in that case).
- Output: `Sentiment_30d` ∈ [-1, +1], `Sentiment_Trend` (latest 7d minus prior 23d).

### EPS revisions and SUE (M9)

- Source: FMP `/analyst-estimates` (the free tier's revision data is sparse but usable for major US names; sparse for EU mid-cap).
- Output columns: `EPS_Rev_30d`, `EPS_Rev_90d`, `SUE` (Standardised Unexpected Earnings z-score).
- Limitation: free-tier estimate history is shallow → SUE coverage is patchy; ST presets that depend on SUE skip the gate when NaN.

### Prices for momentum, vol, and backtest

- yfinance is the reliable source for OHLCV (FMP free tier limits historical price-history depth to 5y).
- 5y daily history per ticker, cached 24h.
- Used by: `momentum_score` (12-1, RS_3m, MA crossings, volume surge), `risk_score_real` (1y vol, 3y MaxDD, 5y monthly Beta), `walk_forward.py` backtest engine.

---

## 7. Known gaps

| Gap | Impact | Mitigation in v2 |
|---|---|---|
| FMP free tier returns 404 for many Euronext tickers | Statement fields NaN for affected EU mid-caps | yfinance fallback covers most; `data_completeness` reports the rest |
| FMP `.AS` → `.AMS` mapping not 100% reliable | Partial ASML.AS, HEIA.AS data | Per-ticker retry with original symbol; logged in `field_sources` |
| FMP free tier lacks `currentRatio`, `debtToEquity` directly | yfinance-only for those fields | No scoring impact (yfinance reliable here) |
| FMP uses GICS sector taxonomy, yfinance uses Yahoo's | Sector-relative scoring may drift on a handful of tickers (e.g. "Technology" vs "Information Technology") | Documented; sector canonicalisation tracked as a known risk |
| FMP free-tier estimate history is shallow | SUE / EPS revision coverage is patchy for EU mid-caps | ST presets skip the gate when NaN; M14 plan: backfill via Finnhub when budget allows |
| Beneish M-Score requires 2 years of statements | Sub-3y listings get `M_Score = NaN` and dropped from `EarningsQuality_Score` | Acceptable: pre-IPO honeymoon should be excluded by `min_years_listed >= 3` anyway |
| FMP 5-year history cap | Multi-period CAGRs (5y rev, 5y EPS) computable; 10y not | Acceptable for v2 — 5y captures one full cycle for most names |
| yfinance can break silently | All-NaN rows → `data_completeness ~ 0`, dropped by gates | Logged as warnings; coverage report flags affected tickers |
| Currency translation | All values in reporting currency (USD for US, EUR for Euronext, etc.) | Out of scope for v2; FX-aware portfolio module queued post-M14 |
| Insider transactions | Not exposed via FMP free tier | Out of scope; would require Finnhub or Whale Wisdom integration |

---

## 8. Future migration: EODHD

If PEA universe coverage proves insufficient in production (large fraction of mid-caps falling to yfinance with sparse statements), **EODHD** is the next-most-likely upgrade:

- **EU coverage** is best-in-class (Euronext, Frankfurt, Milan, Oslo, Madrid full statements).
- **Cost**: Free tier 20 calls/day; paid tier from $19.99/mo unlocks 100K calls/day.
- **Migration**: implement `EODHDDataFetcher(MarketDataSource)` in `backend/app/services/market_data/eodhd_fetcher.py`; insert it into the `HybridDataFetcher` chain ahead of yfinance (or in front of FMP for EU tickers via the symbol-suffix dispatcher). The Protocol means no scoring code changes.

The decision will hinge on a coverage report on the live PEA universe — if `data_completeness` median drops below 0.7 across the universe, EODHD lands in M14+. The track is documented for traceability, not committed.

---

## 9. .env file structure

Copy `.env.example` to `.env` (gitignored) and fill in:

```bash
# .env (NEVER commit this file)

# Required for FMP fundamentals (free tier 250 calls/day)
FMP_TOKEN=your_fmp_key_here

# Optional — only used by /api/scrape endpoints (not in the scoring path)
ALPHA_VANTAGE_KEY=
FINNHUB_KEY=
EODHD_KEY=
```

If `FMP_TOKEN` is unset OR `fmp.enabled: false` in settings.yaml, the engine runs yfinance-only — `data_completeness` will drop on EU statement-heavy fields, and DCF will be NaN on more tickers, but every other path stays functional.

### Security rules

1. **Never commit `.env`** — `.gitignore` includes `.env` and `.env.*`.
2. Use `python-dotenv` to load (handled by `backend/app/config.py`).
3. Store backup of keys in a password manager.
4. Rotate keys if exposed (gitleaks / trufflehog should catch accidental commits but they're not in CI yet — manual review for now).
5. Use free tiers wisely — the 24h cache is the difference between sustainable use and burning a week of quota in a single batch.

---

## 10. References

- ADR for the hybrid choice: [`docs/adr/0002-fmp-yfinance-hybrid.md`](adr/0002-fmp-yfinance-hybrid.md).
- ADR for no-fabrication policy: [`docs/adr/0004-no-fabricated-values.md`](adr/0004-no-fabricated-values.md).
- Live coverage matrix: [`backend/app/services/market_data/coverage_matrix.md`](../backend/app/services/market_data/coverage_matrix.md).
- Source modules:
  - `backend/app/services/market_data/protocol.py` — Protocol contract.
  - `backend/app/services/market_data/fmp_fetcher.py` — FMP implementation.
  - `backend/app/services/market_data/yfinance_fetcher.py` — yfinance implementation.
  - `backend/app/services/market_data/hybrid_fetcher.py` — orchestrator.
  - `backend/app/services/cache_service.py` — JSON-on-disk cache.
  - `scripts/coverage_report.py` — generates the coverage matrix per ticker.
- External: FMP docs (`https://financialmodelingprep.com/developer/docs`), yfinance README (`https://pypi.org/project/yfinance/`), EODHD docs (`https://eodhd.com/financial-apis/`).
