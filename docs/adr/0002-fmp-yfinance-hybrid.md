# ADR 0002: FMP + yfinance Hybrid via Protocol Pattern

**Status:** Accepted
**Date:** 2026-05-08
**Authors:** Tom S, Claude (Opus 4.7)

---

## Context

The v1 data layer was yfinance-only. yfinance is a free unofficial scraper of Yahoo Finance and is reliable for prices, market cap, basic info, and price history. Its weakness is in income statement / balance sheet / cash flow detail — many fields are missing or stale, particularly for non-US tickers.

The 2026-05-08 audit (`AUDIT_2026-05-08_Screener_Metrics.md` §1.1, §1.2, §1.4) showed that the audit-flagged "fabricated values" (`EBIT = EBITDA`, `interest_expense = totalDebt × 0.04`, `working_capital = cash − 0.3 × debt`, `retained_earnings = 0.4 × equity`) were all *workarounds* for fields yfinance doesn't expose reliably. As the audit put it (§1.1):

> Pull `tk.financials.loc['EBIT']` (yfinance does expose it through the income statement, just not in `.info`).

That works in principle, but `tk.financials` is itself patchy for European mid-caps. Combined with the audit's broader recommendation (§4):

> yfinance-only for fundamentals → yfinance for prices, FMP/EODHD for fundamentals (PEA-relevant: EODHD has best EU coverage) — Avoids the EBIT/RE/working-capital workarounds entirely.

…we faced two design questions:

1. **Which paid backend?** Financial Modeling Prep (FMP), EODHD, Finnhub, or a combination.
2. **How to integrate it?** A hard switch (drop yfinance entirely), a Strategy-pattern source-per-ticker, or a hybrid per-field fallback.

### Constraints

- The project is solo-developed and budget-conscious. The FMP free tier (250 calls/day, 5 years of history) is enough for the daily scoring pipeline if combined with aggressive caching.
- yfinance is **free** and does **prices and price history** at least as well as FMP — no reason to pay for OHLCV data.
- EU coverage is uneven across providers. FMP free is US-strong / EU-sparse. EODHD is EU-strong but more expensive. yfinance is mediocre across the board but covers everything Yahoo covers.
- The PEA universe spans Euronext (Paris, Amsterdam, Brussels), Frankfurt, Milan, etc. — exactly the names where FMP free tier is weakest.

The risk of committing to a single backend: when that backend misses a field for a given ticker, the entire ticker is unscoreable. Per-ticker fallbacks would mean scattering "if FMP missing, try yfinance" branches throughout the data layer.

---

## Decision

Adopt a **Protocol-based hybrid** with **per-field fallback**:

1. Define `MarketDataSource` (`backend/app/services/market_data/protocol.py`) as a `typing.Protocol` with eight `fetch_*` methods (quote, fundamentals_annual, fundamentals_quarterly, price_history, eps_estimates, eps_revisions, analyst_targets, news, profile). Methods a concrete source cannot supply must raise `NotImplementedError` (not return NaN) so the orchestrator can distinguish "unsupported by this backend" from "this ticker has no data".

2. Implement two concrete backends today, with the option to add more later:
   - `FMPDataFetcher` — primary fundamentals source (`backend/app/services/market_data/fmp_fetcher.py`).
   - `YFinanceDataFetcher` — fallback (`backend/app/services/market_data/yfinance_fetcher.py`).

3. Implement `HybridDataFetcher` (`backend/app/services/market_data/hybrid_fetcher.py`) as the orchestrator:
   - Try FMP first for every scoring field.
   - On `FMPQuotaExceeded` / `FMPHTTPError(404|429|5xx)` / `NotImplementedError` / NaN-back, try yfinance.
   - On both failing → NaN with `source="missing"`.

4. Carry a parallel `field_sources` dict alongside every fetched row, so callers can compute `data_completeness` honestly per ticker.

5. Cache aggressively (`backend/app/services/cache_service.py`): fundamentals 24h, prices 1h, news 1h, FMP quota tracker (`data/cache/fmp_quota.json`) persistent.

6. Add a kill-switch: `fmp.enabled: false` in `settings.yaml` bypasses FMP entirely (useful for offline development and CI).

7. Add a daily-quota cap in `settings.yaml` (`fmp.daily_limit: 240`), set conservatively below the 250-call free-tier limit.

The Protocol means a future EODHD or Finnhub integration is a one-class addition. No scoring-engine code changes; just register the new backend in the hybrid chain.

---

## Consequences

### Positive

- **Per-field fallback** is granular. A ticker missing only `Revenue` from FMP but full on yfinance produces a complete row, not a half-empty one. `data_completeness` accurately reflects what's present and from where.
- **Honest provenance**. Every value carries `source ∈ {"fmp", "yfinance", "missing"}`. The coverage matrix (`backend/app/services/market_data/coverage_matrix.md`) is generated from real `field_sources` audits, not estimates.
- **Quota safety**. The 240-call cap and 24h cache mean a daily refresh of ~25 new tickers stays well within the free tier. Worst case (full-universe refresh, no cache) is ~1,800 calls — explicitly documented as too aggressive for free tier.
- **Kill-switch**. `fmp.enabled: false` lets the engine run yfinance-only for offline dev and CI tests that don't have a key. CI doesn't burn quota.
- **Future-proof**. Adding EODHD or Finnhub later is registering a new `MarketDataSource` impl in the chain. No scoring code changes — see "Future migration" in [`docs/DATA_SOURCES.md`](../DATA_SOURCES.md) §8.
- **Bug elimination**. The fabricated values from v1 are gone — when yfinance and FMP both miss a field, the engine returns NaN, not an invented proxy. See [ADR-0004](0004-no-fabricated-values.md).

### Negative / trade-offs

- **Two HTTP libraries**. `httpx` is preferred but `requests` is a fallback (older Pythons / restricted environments). The dual codepath is a few lines but adds a tiny test surface.
- **Cache-staleness risk**. 24h fundamentals cache means an earnings release on Tuesday morning won't show in scores until Wednesday morning. Mitigated by exposing `last_updated` in the API response, but a manual cache-bust endpoint would be a useful M14+ addition.
- **Symbol-mapping fragility**. yfinance and FMP disagree on suffixes for some EU exchanges (`.AS` vs `.AMS`, etc.). `_to_fmp_symbol()` in `fmp_fetcher.py` handles the common cases; edge cases produce a 404 → fall through to yfinance, which is correct behaviour but fattens the log.
- **Sector taxonomy drift**. FMP uses GICS, yfinance uses Yahoo's taxonomy. Sector-relative scoring (M3) ranks against peers; if a ticker's sector label disagrees between sources, the rank can drift. Documented in the coverage matrix; canonicalisation is tracked as a known risk.
- **Quota tracking is process-local**. `fmp_quota.json` is a single JSON file with no locking. If two processes run the backend concurrently they can both think they have quota left and overshoot the cap. Acceptable for solo-developer scale; would need a Redis or sqlite lock for production multi-process deployment.
- **Free-tier history limit**. FMP free tier returns 5 years of history, blocking 10y backtests. For now the M12 backtest uses 5y; longer windows are out of scope until a paid tier is in play.
- **Test cost**. The hybrid layer doubled the data-layer test surface (`tests/test_hybrid_fetcher.py`, `tests/test_yfinance_fetcher.py`). Live tests are gated by `pytest -m live` so CI doesn't depend on external services.

---

## Alternatives considered

### Alternative 1: Stay yfinance-only, do better proxies for the missing fields

**Rejected because** the audit's whole point was that proxies are silent corruption. Extending the proxy approach (e.g. compute working capital from quarterly cash flow trends) just trades one fabrication for another. The fabrications would be slightly less wrong but they'd still be fabrications.

### Alternative 2: Pay for FMP starter tier ($14/mo) + drop yfinance entirely

**Rejected because** even on the paid starter plan, FMP's EU mid-cap coverage is partial. Some Euronext tickers (HEIA.AS, AIR.PA at certain points) return 404 on key statement endpoints. Going FMP-only would re-create the "field missing → ticker unscoreable" problem on the EU side, which is exactly the universe we care about most.

### Alternative 3: EODHD as primary, yfinance as fallback, no FMP

**Rejected (for now) because** EODHD's free tier is 20 calls/day — too tight for the daily refresh. The paid tier ($19.99/mo) is affordable but the project is at a stage where committing to a recurring cost is premature. The Protocol design means swapping FMP→EODHD later is a one-class change; the architecture is the right size for both.

### Alternative 4: Per-ticker source dispatch (US tickers → FMP, EU tickers → yfinance)

**Rejected because** the per-field-fallback pattern is strictly more granular. A US ticker with FMP gaps still benefits from yfinance fill-in; an EU ticker that happens to be FMP-covered still uses FMP first. Routing by ticker class is a coarser version of routing by field.

### Alternative 5: Aggressive parallel fetch (FMP + yfinance simultaneously, take the union)

**Rejected because** it doubles the FMP quota burn for marginal benefit. The hybrid's "FMP first, yfinance only when needed" pattern minimises FMP calls. Parallel fetch would make every full-row fetch a 2× cost — incompatible with the 240/day budget.

---

## References

- Audit: research vault, `AUDIT_2026-05-08_Screener_Metrics.md` §§1.1–1.4 (fabricated EBIT, fabricated interest expense, fictitious Altman inputs), §4 (recommendations).
- Methodology v2: research vault, `METHODOLOGY_v2.md` §1 ("Data layer — change before anything else").
- Implementation:
  - `backend/app/services/market_data/protocol.py` — Protocol + `FetchedField` dataclass.
  - `backend/app/services/market_data/fmp_fetcher.py` — FMP backend with quota tracker.
  - `backend/app/services/market_data/yfinance_fetcher.py` — yfinance fallback.
  - `backend/app/services/market_data/hybrid_fetcher.py` — orchestrator + per-field fallback.
  - `backend/app/services/market_data/coverage_matrix.md` — live coverage matrix.
  - `backend/app/services/cache_service.py` — JSON-on-disk cache.
  - `data/cache/fmp_quota.json` — quota persistence.
- Settings: `settings.yaml` `data:`, `fmp:` blocks.
- Companion docs: [`docs/DATA_SOURCES.md`](../DATA_SOURCES.md), [`docs/adr/0004-no-fabricated-values.md`](0004-no-fabricated-values.md).
