"""
Invest Solo -- HybridDataFetcher
Orchestrates per-field FMP-first fallback to yfinance.

Design
------
1. Try FMP for each scoring field.
2. On FMPQuotaExceeded or NotImplementedError or FMPHTTPError(4xx), fall
   through to yfinance.
3. On yfinance failure, return NaN with source="missing".
4. Every field in the returned dict also appears in ``field_sources`` so
   callers know the provenance of each value -- feeding M5's coverage matrix
   and the per-ticker ``data_completeness`` metric.

Public surface matches the legacy DataFetcher so ``data_fetcher.py`` can
delegate without changing ``dependencies.py``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.config import settings
from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.computed_fallback import apply_computed_fallback
from backend.app.services.market_data.fmp_fetcher import (
    FMPDataFetcher,
    FMPHTTPError,
    FMPQuotaExceeded,
)
from backend.app.services.market_data.yfinance_fetcher import (
    YFinanceDataFetcher,
    _is_finite_number,
    _safe_div,
)

# Import SCORING_COLUMNS / EXTRA_FIELDS from the canonical location (data_fetcher)
# to avoid circular imports. We do a lazy import inside the method bodies.

# Fields the FMP extract_scoring_fields() supplies vs yfinance fallback.
# Source attribution: "fmp" if FMP returned a finite value, "yfinance" if yfinance
# filled it in, "missing" if both failed.
_FMP_SUPPLIED_FIELDS = {
    "Revenue",
    "EBITDA",
    "EBIT",
    "NetIncome",
    "OperatingCashflow",
    "FCF",
    "CapEx",
    "TotalAssets",
    "TotalEquity",
    "TotalDebt",
    "Cash",
    "CurrentAssets",
    "CurrentLiabilities",
    "RetainedEarnings",
    "GrossMargin",
    "OperatingMargin",
    "NetMargin",
    "RevenueGrowth",
    "ROE",
    "ROA",
    # M4 — Year-over-Year prior-period inputs for Piotroski deltas
    "LongTermDebt",
    "LongTermDebt_PriorYear",
    "ROA_PriorYear",
    "OperatingCashflow_PriorYear",
    "CurrentRatio_PriorYear",
    "GrossMargin_PriorYear",
    "Revenue_PriorYear",
    "TotalAssets_PriorYear",
    # M5 — Beneish prior-year inputs (scalars)
    "Receivables",
    "Receivables_PriorYear",
    "CurrentAssets_PriorYear",
    "CurrentLiabilities_PriorYear",
    "PPE",
    "PPE_PriorYear",
    "DepreciationAmortization",
    "DepreciationAmortization_PriorYear",
    "SGA",
    "SGA_PriorYear",
    "COGS",
    "InterestExpense",
}

# M5: list-valued history columns that override scalars-only `_is_valid` checks.
_FMP_SUPPLIED_HISTORY_FIELDS = {
    "FCF_History_5y",
    "NetIncome_History_5y",
    "ROIC_History_5y",
    "OperatingMargin_History_5y",
    "EBIT_History_3y",
    "InvestedCapital_History_3y",
}


class HybridDataFetcher:
    """FMP-first hybrid data fetcher with per-field yfinance fallback.

    Parameters
    ----------
    fmp:
        FMPDataFetcher instance.
    yf:
        YFinanceDataFetcher instance.
    cache:
        Shared CacheService instance (reused by both sub-fetchers).
    """

    def __init__(
        self,
        fmp: FMPDataFetcher,
        yf: YFinanceDataFetcher,
        cache: CacheService,
    ) -> None:
        self._fmp = fmp
        self._yf = yf
        self._cache = cache
        self._pea_countries = settings.pea_eligible_countries
        self._delay = settings.request_delay_seconds

    # ------------------------------------------------------------------
    # Public API (matches legacy DataFetcher surface)
    # ------------------------------------------------------------------

    def fetch_single(
        self,
        ticker: str,
        cache_only: bool = False,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        """Fetch a complete scoring row for *ticker* from the requested source.

        ``source`` is one of ``"hybrid"`` (default — current behavior),
        ``"yfinance"`` (yfinance only, FMP skipped), or ``"fmp"`` (FMP only,
        with explicit fallback to yfinance when FMP is unavailable; the
        returned dict carries ``effective_source`` and
        ``source_fallback_message`` so the caller can tell the user).
        """
        from backend.app.services.market_data.types import is_valid_source

        if not is_valid_source(source):
            raise ValueError(f"Unknown source {source!r}; expected one of hybrid/yfinance/fmp")

        cache_key = f"{source}:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"{source} cache hit for {ticker}")
            return cached

        if source == "yfinance":
            return self._fetch_yfinance_only(ticker, cache_key, cache_only)
        if source == "fmp":
            return self._fetch_fmp_only(ticker, cache_key, cache_only)

        return self._fetch_hybrid(ticker, cache_key, cache_only)

    def _fetch_hybrid(
        self,
        ticker: str,
        cache_key: str,
        cache_only: bool,
    ) -> dict[str, Any]:
        """Original hybrid (FMP-first + yfinance fallback) flow."""
        from backend.app.services.data_fetcher import EXTRA_FIELDS, SCORING_COLUMNS

        if cache_only:
            logger.debug(f"cache_only=True, cache miss for {ticker}: returning NaN row")
            return self._nan_row(ticker, "hybrid", None)

        logger.info(f"HybridDataFetcher: assembling row for {ticker}")

        # ------------------------------------------------------------------
        # Step 1: yfinance full row as base (always)
        # ------------------------------------------------------------------
        yf_row: dict[str, Any] = {}
        try:
            yf_row = self._yf.fetch_full_row(ticker)
        except Exception as exc:
            logger.warning(f"yfinance fetch_full_row failed for {ticker}: {exc}")

        result: dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        result["Ticker"] = ticker
        field_sources: dict[str, str] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}

        # Apply yfinance values
        for k, v in yf_row.items():
            if k in result:
                result[k] = v
                if k in SCORING_COLUMNS or k in EXTRA_FIELDS:
                    field_sources[k] = "yfinance" if self._is_valid(v) else "missing"

        # Populate identification fields (always from yfinance/yf_row)
        for id_field in ("Name", "Sector", "Industry", "Country", "Exchange", "PEA", "PEA_PME"):
            if id_field in yf_row:
                result[id_field] = yf_row[id_field]

        # ------------------------------------------------------------------
        # Step 2: FMP overlay for fundamental fields
        # ------------------------------------------------------------------
        fmp_fields: dict[str, Any] = {}
        try:
            fmp_fields = self._fmp.extract_scoring_fields(ticker)
        except FMPQuotaExceeded as exc:
            logger.info(f"FMP quota/disabled for {ticker}: {exc} -- using yfinance only")
        except Exception as exc:
            logger.warning(f"FMP extract_scoring_fields failed for {ticker}: {exc}")

        # Overlay FMP values for fields it covers (only if finite)
        for scoring_col in _FMP_SUPPLIED_FIELDS:
            fmp_val = fmp_fields.get(scoring_col, np.nan)
            if self._is_valid(fmp_val):
                result[scoring_col] = float(fmp_val)
                field_sources[scoring_col] = "fmp"

        # M5: overlay list-valued history fields. Treated as "valid" when
        # non-empty, regardless of element-wise finiteness (the consumers
        # filter for finiteness internally).
        for hist_col in _FMP_SUPPLIED_HISTORY_FIELDS:
            fmp_seq = fmp_fields.get(hist_col)
            if isinstance(fmp_seq, list) and len(fmp_seq) >= 1:
                result[hist_col] = list(fmp_seq)
                field_sources[hist_col] = "fmp"

        # M5: WACC placeholder. M6 will fill with the real value.
        result.setdefault("WACC", np.nan)

        # FMP supplies EBIT as operatingIncome which is the right value.
        # If we got a valid FMP EBIT and the yfinance one was NaN, we've improved.
        # InterestExpense_FMP: use to compute InterestCoverage if FMP has EBIT
        ie_fmp = fmp_fields.get("InterestExpense_FMP", np.nan)
        if self._is_valid(ie_fmp) and self._is_valid(result.get("EBIT")):
            ie = abs(float(ie_fmp))
            if ie > 0:
                ic = float(result["EBIT"]) / ie
                result["InterestCoverage"] = ic
                field_sources["InterestCoverage"] = "fmp"

        # ------------------------------------------------------------------
        # Step 3: FMP quote overlay for price/market data
        # ------------------------------------------------------------------
        fmp_quote: dict[str, Any] = {}
        try:
            fmp_quote = self._fmp.fetch_quote(ticker)
        except FMPQuotaExceeded:
            pass
        except Exception as exc:
            logger.debug(f"FMP fetch_quote failed for {ticker}: {exc}")

        for fmp_key, scoring_key in [
            ("Price", "Price"),
            ("MarketCap", "MarketCap"),
            ("EV", "EV"),
            ("Shares", "Shares"),
            ("Beta", "Beta"),
            ("AvgVolume", "AvgVolume"),
            ("FiftyTwoWeekHigh", "FiftyTwoWeekHigh"),
            ("FiftyTwoWeekLow", "FiftyTwoWeekLow"),
            ("PE", "PE"),
        ]:
            fmp_val = fmp_quote.get(fmp_key)
            if self._is_valid(fmp_val):
                result[scoring_key] = float(fmp_val)
                field_sources[scoring_key] = "fmp"

        # ------------------------------------------------------------------
        # Step 4: Re-derive computed ratios using best available inputs
        # ------------------------------------------------------------------
        self._recompute_derived(result, field_sources)

        # ------------------------------------------------------------------
        # Step 5: PEA eligibility (always from country code)
        # ------------------------------------------------------------------
        country = result.get("Country", "")
        if isinstance(country, str) and country:
            result["PEA"] = country.upper() in self._pea_countries
            mktcap = result.get("MarketCap", 0) or 0
            result["PEA_PME"] = result["PEA"] and (0 < mktcap < 2_000_000_000)
        else:
            result.setdefault("PEA", False)
            result.setdefault("PEA_PME", False)

        # ------------------------------------------------------------------
        # Step 6: data_completeness + source bookkeeping
        # ------------------------------------------------------------------
        self._inject_analyst_signals(ticker, result, field_sources)
        apply_computed_fallback(result, field_sources)
        result["data_completeness"] = self._completeness(result)
        result["field_sources"] = field_sources
        result["effective_source"] = "hybrid"
        result["source_fallback_message"] = None

        # Cache 4 hours
        self._cache.set(cache_key, result, ttl_seconds=14400)
        return result

    # ------------------------------------------------------------------
    # Source-specific branches
    # ------------------------------------------------------------------

    def _fetch_yfinance_only(
        self,
        ticker: str,
        cache_key: str,
        cache_only: bool,
    ) -> dict[str, Any]:
        """yfinance-only flow. FMP is never consulted."""
        from backend.app.services.data_fetcher import EXTRA_FIELDS, SCORING_COLUMNS

        if cache_only:
            return self._nan_row(ticker, "yfinance", None)

        logger.info(f"yfinance-only: assembling row for {ticker}")
        yf_row: dict[str, Any] = {}
        try:
            yf_row = self._yf.fetch_full_row(ticker)
        except Exception as exc:
            logger.warning(f"yfinance fetch_full_row failed for {ticker}: {exc}")

        result: dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        result["Ticker"] = ticker
        field_sources: dict[str, str] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}

        for k, v in yf_row.items():
            if k in result:
                result[k] = v
                if k in SCORING_COLUMNS or k in EXTRA_FIELDS:
                    field_sources[k] = "yfinance" if self._is_valid(v) else "missing"

        for id_field in ("Name", "Sector", "Industry", "Country", "Exchange", "PEA", "PEA_PME"):
            if id_field in yf_row:
                result[id_field] = yf_row[id_field]

        country = result.get("Country", "")
        if isinstance(country, str) and country:
            result["PEA"] = country.upper() in self._pea_countries
            mktcap = result.get("MarketCap", 0) or 0
            result["PEA_PME"] = result["PEA"] and (0 < mktcap < 2_000_000_000)
        else:
            result.setdefault("PEA", False)
            result.setdefault("PEA_PME", False)

        self._inject_analyst_signals(ticker, result, field_sources)
        apply_computed_fallback(result, field_sources)
        result["data_completeness"] = self._completeness(result)
        result["field_sources"] = field_sources
        result["effective_source"] = "yfinance"
        result["source_fallback_message"] = None
        self._cache.set(cache_key, result, ttl_seconds=14400)
        return result

    def _fetch_fmp_only(
        self,
        ticker: str,
        cache_key: str,
        cache_only: bool,
    ) -> dict[str, Any]:
        """fmp-only flow with explicit yfinance fallback on FMP unavailability.

        On ``FMPQuotaExceeded``, ``FMPHTTPError``, or when FMP is disabled in
        settings, returns a yfinance-sourced row with
        ``effective_source="yfinance"`` plus a ``source_fallback_message``
        explaining what happened.
        """
        from backend.app.services.data_fetcher import EXTRA_FIELDS, SCORING_COLUMNS

        if cache_only:
            return self._nan_row(ticker, "fmp", None)

        if not getattr(self._fmp, "_enabled", True):
            logger.info(f"FMP disabled, falling back to yfinance for {ticker}")
            return self._fallback_to_yfinance(
                ticker,
                cache_key,
                msg="FMP source is disabled in settings; using yfinance.",
            )

        logger.info(f"fmp-only: assembling row for {ticker}")
        try:
            fmp_fields = self._fmp.extract_scoring_fields(ticker)
            fmp_quote = self._fmp.fetch_quote(ticker)
        except FMPQuotaExceeded as exc:
            logger.info(f"FMP quota exceeded for {ticker}: {exc}; falling back to yfinance")
            return self._fallback_to_yfinance(
                ticker,
                cache_key,
                msg="FMP daily quota exhausted; using yfinance for this fetch.",
            )
        except FMPHTTPError as exc:
            logger.warning(f"FMP HTTP error for {ticker}: {exc}; falling back to yfinance")
            return self._fallback_to_yfinance(
                ticker,
                cache_key,
                msg=f"FMP returned an error ({exc}); using yfinance.",
            )

        result: dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        result["Ticker"] = ticker
        field_sources: dict[str, str] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}

        for scoring_col in _FMP_SUPPLIED_FIELDS:
            val = fmp_fields.get(scoring_col, np.nan)
            if self._is_valid(val):
                result[scoring_col] = float(val)
                field_sources[scoring_col] = "fmp"

        for hist_col in _FMP_SUPPLIED_HISTORY_FIELDS:
            seq = fmp_fields.get(hist_col)
            if isinstance(seq, list) and len(seq) >= 1:
                result[hist_col] = list(seq)
                field_sources[hist_col] = "fmp"

        # FMP raw InterestExpense → derive InterestCoverage when EBIT available.
        ie_fmp = fmp_fields.get("InterestExpense_FMP", np.nan)
        if self._is_valid(ie_fmp) and self._is_valid(result.get("EBIT")):
            ie = abs(float(ie_fmp))
            if ie > 0:
                result["InterestCoverage"] = float(result["EBIT"]) / ie
                field_sources["InterestCoverage"] = "fmp"

        for fmp_key in (
            "Price",
            "MarketCap",
            "EV",
            "Shares",
            "Beta",
            "AvgVolume",
            "FiftyTwoWeekHigh",
            "FiftyTwoWeekLow",
            "PE",
        ):
            val = fmp_quote.get(fmp_key)
            if self._is_valid(val):
                result[fmp_key] = float(val)
                field_sources[fmp_key] = "fmp"

        self._recompute_derived(result, field_sources)

        country = result.get("Country", "")
        if isinstance(country, str) and country:
            result["PEA"] = country.upper() in self._pea_countries
            mktcap = result.get("MarketCap", 0) or 0
            result["PEA_PME"] = result["PEA"] and (0 < mktcap < 2_000_000_000)
        else:
            result.setdefault("PEA", False)
            result.setdefault("PEA_PME", False)

        self._inject_analyst_signals(ticker, result, field_sources)
        apply_computed_fallback(result, field_sources)
        result["data_completeness"] = self._completeness(result)
        result["field_sources"] = field_sources
        result["effective_source"] = "fmp"
        result["source_fallback_message"] = None
        self._cache.set(cache_key, result, ttl_seconds=14400)
        return result

    def _fallback_to_yfinance(
        self,
        ticker: str,
        cache_key: str,
        msg: str,
    ) -> dict[str, Any]:
        """Build a yfinance-sourced row and mark it as the FMP fallback."""
        from backend.app.services.data_fetcher import EXTRA_FIELDS, SCORING_COLUMNS

        yf_row: dict[str, Any] = {}
        try:
            yf_row = self._yf.fetch_full_row(ticker)
        except Exception as exc:
            logger.warning(f"yfinance fallback failed for {ticker}: {exc}")

        result: dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        result["Ticker"] = ticker
        field_sources: dict[str, str] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}
        for k, v in yf_row.items():
            if k in result:
                result[k] = v
                if k in SCORING_COLUMNS or k in EXTRA_FIELDS:
                    field_sources[k] = "yfinance" if self._is_valid(v) else "missing"
        for id_field in ("Name", "Sector", "Industry", "Country", "Exchange", "PEA", "PEA_PME"):
            if id_field in yf_row:
                result[id_field] = yf_row[id_field]

        country = result.get("Country", "")
        if isinstance(country, str) and country:
            result["PEA"] = country.upper() in self._pea_countries
            mktcap = result.get("MarketCap", 0) or 0
            result["PEA_PME"] = result["PEA"] and (0 < mktcap < 2_000_000_000)
        else:
            result.setdefault("PEA", False)
            result.setdefault("PEA_PME", False)

        self._inject_analyst_signals(ticker, result, field_sources)
        apply_computed_fallback(result, field_sources)
        result["data_completeness"] = self._completeness(result)
        result["field_sources"] = field_sources
        result["effective_source"] = "yfinance"
        result["source_fallback_message"] = msg
        self._cache.set(cache_key, result, ttl_seconds=14400)
        return result

    def _nan_row(
        self,
        ticker: str,
        effective: str,
        fallback_msg: str | None,
    ) -> dict[str, Any]:
        """Build an all-NaN row with consistent provenance bookkeeping."""
        from backend.app.services.data_fetcher import EXTRA_FIELDS, SCORING_COLUMNS

        row: dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        row["Ticker"] = ticker
        row["field_sources"] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}
        row["data_completeness"] = 0.0
        row["PEA"] = False
        row["PEA_PME"] = False
        row["effective_source"] = effective
        row["source_fallback_message"] = fallback_msg
        return row

    @staticmethod
    def _completeness_excluded_fields() -> set[str]:
        return {
            "Name",
            "Sector",
            "Industry",
            "Country",
            "Exchange",
            "PEA",
            "PEA_PME",
            # M5 additions (excluded to keep completeness stable across milestones)
            "FCF_History_5y",
            "NetIncome_History_5y",
            "ROIC_History_5y",
            "OperatingMargin_History_5y",
            "EBIT_History_3y",
            "InvestedCapital_History_3y",
            "Receivables",
            "Receivables_PriorYear",
            "Revenue_PriorYear",
            "GrossMargin_PriorYear",
            "TotalAssets_PriorYear",
            "CurrentAssets_PriorYear",
            "PPE",
            "PPE_PriorYear",
            "DepreciationAmortization",
            "DepreciationAmortization_PriorYear",
            "SGA",
            "SGA_PriorYear",
            "LongTermDebt",
            "LongTermDebt_PriorYear",
            "CurrentLiabilities_PriorYear",
            "COGS",
            "InterestExpense",
            "WACC",
            # Sub-project 2 — display-only analyst counts/values that default
            # to 0 even when "no data" and would falsely inflate completeness.
            # SUE / EpsRevision30d / EpsRevision90d remain in the denominator
            # since they are real Momentum-feeding scoring signals.
            "EarningsSurprise",
            "GrowthEstimateFY",
            "EpsRevisionsUp30d",
            "EpsRevisionsDown30d",
        }

    def _inject_analyst_signals(
        self,
        ticker: str,
        result: dict[str, Any],
        sources: dict[str, str],
    ) -> None:
        """Pull yfinance.analysis data and populate the dormant scoring fields.

        Always uses yfinance (FMP analyst data is not wired in sub-project 2).
        Per-method failures are swallowed; the row stays valid.

        Formulas locked in by Phase 0 financial review:
        - SUE: surprises[0] / stdev(surprises[1:], ddof=1) — current quarter
          excluded from σ (Bernard-Thomas 1989); requires ≥ 6 quarters.
        - EpsRevision30d/90d: (current - past) / abs(past) with abs() to
          preserve sign on negative prior estimates.
        - EarningsSurprise: latest quarter's surprisePercent from yfinance.
        - GrowthEstimateFY: stockTrend for +1y row from tk.growth_estimates.
        """
        from src.analysis.analyst_signals import (
            compute_eps_revision_pct_from_trend,
            compute_sue_from_history,
            earnings_surprise_latest,
        )

        try:
            history = self._yf.fetch_earnings_history(ticker, limit=8)
        except Exception:
            history = []
        try:
            trend = self._yf.fetch_eps_trend(ticker)
        except Exception:
            trend = []
        try:
            rev_counts = self._yf.fetch_eps_revisions(ticker)
        except Exception:
            rev_counts = {}
        try:
            growth = self._yf.fetch_growth_estimates(ticker)
        except Exception:
            growth = {}

        def _set(field: str, value: Any) -> None:
            import math as _math

            if value is None:
                return
            try:
                fv = float(value)
            except (TypeError, ValueError):
                return
            if _math.isnan(fv) or _math.isinf(fv):
                return
            result[field] = fv
            sources[field] = "yfinance"

        _set("SUE", compute_sue_from_history(history))
        _set("EpsRevision30d", compute_eps_revision_pct_from_trend(trend, days=30))
        _set("EpsRevision90d", compute_eps_revision_pct_from_trend(trend, days=90))
        _set("EarningsSurprise", earnings_surprise_latest(history))
        _set("GrowthEstimateFY", growth.get("fy_growth"))
        _set("EpsRevisionsUp30d", rev_counts.get("up_last_30d"))
        _set("EpsRevisionsDown30d", rev_counts.get("down_last_30d"))

    def _completeness(self, result: dict[str, Any]) -> float:
        """Fraction of numeric SCORING_COLUMNS that are finite in *result*."""
        from backend.app.services.data_fetcher import SCORING_COLUMNS

        excluded = self._completeness_excluded_fields()
        numeric_cols = [c for c in SCORING_COLUMNS if c not in excluded]
        n_present = sum(1 for c in numeric_cols if self._is_valid(result.get(c)))
        return n_present / len(numeric_cols) if numeric_cols else 0.0

    def fetch_batch(
        self,
        tickers: list[str],
        source: str = "hybrid",
        *,
        max_workers: int = 1,
        on_ticker_complete: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> pd.DataFrame:
        """Fetch multiple tickers from the requested source.

        ``max_workers`` > 1 enables ``ThreadPoolExecutor`` parallelism (used by
        the SSE refresh stream). ``max_workers=1`` keeps the legacy sequential
        path with ``request_delay_seconds`` between calls — preserves existing
        caller behavior. ``on_ticker_complete(ticker, row)`` is invoked once
        per completed ticker (sequential or parallel) so a streaming consumer
        can push progress events.
        """
        from backend.app.services.data_fetcher import SCORING_COLUMNS

        rows: list[dict[str, Any]] = []

        if max_workers <= 1:
            for i, ticker in enumerate(tickers):
                try:
                    data = self.fetch_single(ticker, source=source)
                except Exception as exc:
                    logger.warning(f"fetch_single({ticker}) raised: {exc}")
                    data = {}
                data["Ticker"] = ticker
                rows.append(data)
                if on_ticker_complete is not None:
                    try:
                        on_ticker_complete(ticker, data)
                    except Exception as exc:
                        logger.debug(f"on_ticker_complete callback raised for {ticker}: {exc}")
                if i < len(tickers) - 1:
                    time.sleep(self._delay)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_ticker = {pool.submit(self.fetch_single, t, source=source): t for t in tickers}
                for future in as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try:
                        data = future.result()
                    except Exception as exc:
                        logger.warning(f"fetch_single({ticker}) raised in worker: {exc}")
                        data = {}
                    data["Ticker"] = ticker
                    rows.append(data)
                    if on_ticker_complete is not None:
                        try:
                            on_ticker_complete(ticker, data)
                        except Exception as exc:
                            logger.debug(f"on_ticker_complete callback raised for {ticker}: {exc}")

        if not rows:
            return pd.DataFrame(columns=["Ticker"] + SCORING_COLUMNS)

        df = pd.DataFrame(rows)
        df.set_index("Ticker", inplace=True)
        return df

    def fetch_analyst_ratings(
        self,
        ticker: str,
        source: str = "hybrid",
    ) -> dict[str, Any] | None:
        """Return the enriched analyst payload (sub-project 2 shape).

        Targets follow the source-routing contract (FMP-first for hybrid/fmp,
        yfinance for yfinance). Rating counts, upgrades, growth estimates, and
        earnings history are always yfinance-only (FMP analyst data not wired).

        Returned dict shape matches ``AnalystRatings`` Pydantic model:
        - buy/hold/sell/strong_buy/strong_sell  (int counts)
        - target_low/mean/high/median           (float | None)
        - num_analysts                          (int | None)
        - recent_changes                        (list of upgrade/downgrade dicts)
        - revisions_history                     (list of {period,up,down})
        - growth_estimate_fy / growth_estimate_5y (float | None)
        - earnings_history                      (list of EarningsHistoryRow dicts)
        """
        from backend.app.services.market_data.types import is_valid_source

        if not is_valid_source(source):
            raise ValueError(f"Unknown source {source!r}")

        # 1. Targets — preserves existing FMP-first/yfinance fallback contract
        targets: dict[str, Any] = {}
        if source != "yfinance":
            try:
                fmp_targets = self._fmp.fetch_analyst_targets(ticker)
                if fmp_targets:
                    targets = fmp_targets
            except (FMPQuotaExceeded, FMPHTTPError):
                pass
            except Exception as exc:
                logger.debug(f"FMP fetch_analyst_targets failed for {ticker}: {exc}")
        if not targets:
            try:
                targets = self._yf.fetch_analyst_targets(ticker) or {}
            except Exception:
                targets = {}

        # 2. yfinance.analysis enrichment — always sourced from yfinance
        try:
            rec = self._yf.fetch_recommendations_summary(ticker)
        except Exception:
            rec = {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
        try:
            upgrades = self._yf.fetch_upgrades_downgrades(ticker, limit=50)[:3]
        except Exception:
            upgrades = []
        try:
            growth = self._yf.fetch_growth_estimates(ticker)
        except Exception:
            growth = {}
        try:
            history = self._yf.fetch_earnings_history(ticker, limit=8)
        except Exception:
            history = []
        try:
            rev_counts = self._yf.fetch_eps_revisions(ticker)
        except Exception:
            rev_counts = {}

        revisions_history = [
            {"period": "7d", "up": rev_counts.get("up_last_7d", 0), "down": rev_counts.get("down_last_7d", 0)},
            {"period": "30d", "up": rev_counts.get("up_last_30d", 0), "down": rev_counts.get("down_last_30d", 0)},
            {"period": "60d", "up": rev_counts.get("up_last_60d", 0), "down": rev_counts.get("down_last_60d", 0)},
            {"period": "90d", "up": rev_counts.get("up_last_90d", 0), "down": rev_counts.get("down_last_90d", 0)},
        ]

        return {
            "buy": rec.get("buy", 0),
            "hold": rec.get("hold", 0),
            "sell": rec.get("sell", 0),
            "strong_buy": rec.get("strong_buy", 0),
            "strong_sell": rec.get("strong_sell", 0),
            "target_low": targets.get("target_low"),
            "target_mean": targets.get("target_mean"),
            "target_high": targets.get("target_high"),
            "target_median": targets.get("target_median"),
            "num_analysts": targets.get("num_analysts"),
            "recent_changes": upgrades,
            "revisions_history": revisions_history,
            "growth_estimate_fy": growth.get("fy_growth"),
            "growth_estimate_5y": growth.get("five_year_growth"),
            "earnings_history": history,
        }

    def fetch_calendar(
        self,
        ticker: str,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        """Forward events + dividend history (sub-project 3 — display-only).

        yfinance is the only backing source; FMP calendar endpoints are
        intentionally unwired. The ``source`` parameter is honored for
        cache-key isolation only, so callers running yfinance/fmp/hybrid
        side-by-side don't cross-contaminate their results.

        Returns the ``CompanyCalendar`` Pydantic shape as a plain dict.
        Individual yfinance fetcher failures degrade gracefully and never
        block the other two fetchers.
        """
        from backend.app.services.market_data.types import is_valid_source

        if not is_valid_source(source):
            raise ValueError(f"Unknown source {source!r}")

        cache_key = f"calendar:{source}:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            cal = self._yf.fetch_calendar(ticker)
        except Exception as exc:
            logger.debug(f"hybrid fetch_calendar (yf.calendar) failed for {ticker}: {exc}")
            cal = {}
        try:
            divs = self._yf.fetch_dividends(ticker, years=5)
        except Exception as exc:
            logger.debug(f"hybrid fetch_calendar (yf.dividends) failed for {ticker}: {exc}")
            divs = []
        try:
            yields = self._yf.fetch_info_yields(ticker)
        except Exception as exc:
            logger.debug(f"hybrid fetch_calendar (yf.info_yields) failed for {ticker}: {exc}")
            yields = {}

        out: dict[str, Any] = {
            "next_earnings_date": cal.get("next_earnings_date"),
            "next_earnings_eps_estimate": cal.get("next_earnings_eps_estimate"),
            "next_earnings_eps_low": cal.get("next_earnings_eps_low"),
            "next_earnings_eps_high": cal.get("next_earnings_eps_high"),
            "next_earnings_revenue_estimate": cal.get("next_earnings_revenue_estimate"),
            "dividend_date": cal.get("dividend_date"),
            "ex_dividend_date": cal.get("ex_dividend_date"),
            "dividend_amount": divs[-1]["amount"] if divs else None,
            "dividend_yield": yields.get("dividend_yield"),
            "dividend_rate": yields.get("dividend_rate"),
            "trailing_annual_dividend_rate": yields.get("trailing_annual_dividend_rate"),
            "trailing_annual_dividend_yield": yields.get("trailing_annual_dividend_yield"),
            "dividends_5y": divs,
        }
        self._cache.set(cache_key, out, ttl_seconds=21600)  # 6h
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid(val: Any) -> bool:
        """True iff val is a finite number."""
        return _is_finite_number(val)

    def _recompute_derived(self, result: dict[str, Any], sources: dict[str, str]) -> None:
        """Re-derive ratio fields from whatever inputs are now available.

        This is idempotent -- it overwrites stale computed values with fresher
        ones when FMP improved the underlying inputs.
        """
        price = result.get("Price")
        ev = result.get("EV")
        rev = result.get("Revenue")
        ebitda = result.get("EBITDA")
        ebit = result.get("EBIT")
        fcf = result.get("FCF")
        shares = result.get("Shares")
        equity = result.get("TotalEquity")
        debt = result.get("TotalDebt")
        cash = result.get("Cash")

        # EV/EBITDA
        if self._is_valid(ev) and self._is_valid(ebitda):
            result["EV_EBITDA"] = _safe_div(ev, ebitda)
            fmp_used = sources.get("EV") == "fmp" or sources.get("EBITDA") == "fmp"
            sources["EV_EBITDA"] = "fmp" if fmp_used else "yfinance"

        # EV/Sales
        if self._is_valid(ev) and self._is_valid(rev):
            result["EV_Sales"] = _safe_div(ev, rev)
            fmp_used = sources.get("EV") == "fmp" or sources.get("Revenue") == "fmp"
            sources["EV_Sales"] = "fmp" if fmp_used else "yfinance"

        # P/FCF
        if self._is_valid(fcf) and fcf > 0 and self._is_valid(shares) and shares > 0 and self._is_valid(price):
            fcf_per_share = float(fcf) / float(shares)
            if fcf_per_share > 0:
                result["PFCF"] = float(price) / fcf_per_share
                fmp_used = sources.get("FCF") == "fmp" or sources.get("Price") == "fmp"
                sources["PFCF"] = "fmp" if fmp_used else "yfinance"

        # FCFMargin
        if self._is_valid(fcf) and self._is_valid(rev) and float(rev) > 0:
            result["FCFMargin"] = float(fcf) / float(rev)
            fmp_used = sources.get("FCF") == "fmp" or sources.get("Revenue") == "fmp"
            sources["FCFMargin"] = "fmp" if fmp_used else "yfinance"

        # ROIC = EBIT*(1-0.25) / (Equity + Debt - Cash)
        if all(self._is_valid(x) for x in [ebit, equity, debt, cash]):
            invested_capital = float(equity) + float(debt) - float(cash)
            if invested_capital > 0:
                result["ROIC"] = (float(ebit) * 0.75) / invested_capital
                fmp_used = any(sources.get(f) == "fmp" for f in ("EBIT", "TotalEquity", "TotalDebt", "Cash"))
                sources["ROIC"] = "fmp" if fmp_used else "yfinance"
            else:
                result.setdefault("ROIC", np.nan)

        # InterestCoverage (if not already set from FMP raw interest expense)
        if "InterestCoverage" not in result or not self._is_valid(result.get("InterestCoverage")):
            # yfinance-derived InterestCoverage may already be in result from yf_row
            pass  # Keep whatever yfinance gave us

        # PS (price/sales per share) -- prefer yfinance ratio, but recompute if
        # FMP gave us revenue and we have price/shares
        if not self._is_valid(result.get("PS")):
            if self._is_valid(price) and self._is_valid(rev) and self._is_valid(shares):
                sh = float(shares)
                if sh > 0:
                    rev_per_share = float(rev) / sh
                    if rev_per_share > 0:
                        result["PS"] = float(price) / rev_per_share
                        sources["PS"] = "fmp" if sources.get("Revenue") == "fmp" else "yfinance"
