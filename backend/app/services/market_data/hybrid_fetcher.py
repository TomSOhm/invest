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
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.config import settings
from backend.app.services.cache_service import CacheService
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
    "Revenue", "EBITDA", "EBIT", "NetIncome",
    "OperatingCashflow", "FCF", "CapEx",
    "TotalAssets", "TotalEquity", "TotalDebt", "Cash",
    "CurrentAssets", "CurrentLiabilities", "RetainedEarnings",
    "GrossMargin", "OperatingMargin", "NetMargin", "RevenueGrowth",
    "ROE", "ROA",
    # M5 Beneish prior-year inputs (scalars)
    "Receivables", "Receivables_PriorYear",
    "Revenue_PriorYear", "GrossMargin_PriorYear",
    "TotalAssets_PriorYear", "CurrentAssets_PriorYear",
    "CurrentLiabilities_PriorYear",
    "PPE", "PPE_PriorYear",
    "DepreciationAmortization", "DepreciationAmortization_PriorYear",
    "SGA", "SGA_PriorYear",
    "LongTermDebt", "LongTermDebt_PriorYear",
    "COGS", "InterestExpense",
}

# M5: list-valued history columns that override scalars-only `_is_valid` checks.
_FMP_SUPPLIED_HISTORY_FIELDS = {
    "FCF_History_5y", "NetIncome_History_5y",
    "ROIC_History_5y", "OperatingMargin_History_5y",
    "EBIT_History_3y", "InvestedCapital_History_3y",
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

    def fetch_single(self, ticker: str) -> Dict[str, Any]:
        """Fetch a complete scoring row for *ticker*.

        Returns a dict with keys matching ``SCORING_COLUMNS + EXTRA_FIELDS``
        plus:
        - ``"field_sources"``: Dict[str, str] mapping each field name to the
          source that provided it (``"fmp"``, ``"yfinance"``, or ``"missing"``).
        - ``"data_completeness"``: fraction of SCORING_COLUMNS that are finite.
        - ``"Ticker"``: the ticker symbol.

        Strategy:
        1. Check the hybrid-level cache (``hybrid:{ticker}``).
        2. Get the yfinance full row as the base (proven by M1).
        3. Overlay FMP fundamental fields where FMP can supply them and they
           are finite.
        4. Fill any remaining NaN from the FMP quote endpoint.
        5. Derive computed fields (ROIC, PFCF, InterestCoverage, etc.) using
           the best available inputs.
        6. Record provenance in ``field_sources``.
        """
        # Lazy import to avoid circular dependency at module load time
        from backend.app.services.data_fetcher import SCORING_COLUMNS, EXTRA_FIELDS

        cache_key = f"hybrid:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Hybrid cache hit for {ticker}")
            return cached

        logger.info(f"HybridDataFetcher: assembling row for {ticker}")

        # ------------------------------------------------------------------
        # Step 1: yfinance full row as base (always)
        # ------------------------------------------------------------------
        yf_row: Dict[str, Any] = {}
        try:
            yf_row = self._yf.fetch_full_row(ticker)
        except Exception as exc:
            logger.warning(f"yfinance fetch_full_row failed for {ticker}: {exc}")

        result: Dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        result["Ticker"] = ticker
        field_sources: Dict[str, str] = {col: "missing" for col in SCORING_COLUMNS + EXTRA_FIELDS}

        # Apply yfinance values
        for k, v in yf_row.items():
            if k in result:
                result[k] = v
                if k in SCORING_COLUMNS or k in EXTRA_FIELDS:
                    field_sources[k] = "yfinance" if self._is_valid(v) else "missing"

        # Populate identification fields (always from yfinance/yf_row)
        for id_field in ("Name", "Sector", "Industry", "Country", "Exchange",
                         "PEA", "PEA_PME"):
            if id_field in yf_row:
                result[id_field] = yf_row[id_field]

        # ------------------------------------------------------------------
        # Step 2: FMP overlay for fundamental fields
        # ------------------------------------------------------------------
        fmp_fields: Dict[str, Any] = {}
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
        fmp_quote: Dict[str, Any] = {}
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
        # Step 6: data_completeness
        # ------------------------------------------------------------------
        # We exclude:
        #   - identification fields (Name, Sector, ...): never numeric
        #   - all M5-added fields: keep the M2 denominator stable so the
        #     `data_completeness` ratio stays comparable across milestones.
        #     M7 will redefine completeness with the new categories included.
        _COMPLETENESS_EXCLUDE = {
            "Name", "Sector", "Industry", "Country", "Exchange",
            "PEA", "PEA_PME",
            # M5 additions (excluded to keep completeness stable across milestones)
            "FCF_History_5y", "NetIncome_History_5y",
            "ROIC_History_5y", "OperatingMargin_History_5y",
            "EBIT_History_3y", "InvestedCapital_History_3y",
            "Receivables", "Receivables_PriorYear",
            "Revenue_PriorYear", "GrossMargin_PriorYear",
            "TotalAssets_PriorYear", "CurrentAssets_PriorYear",
            "PPE", "PPE_PriorYear",
            "DepreciationAmortization", "DepreciationAmortization_PriorYear",
            "SGA", "SGA_PriorYear",
            "LongTermDebt", "LongTermDebt_PriorYear",
            "CurrentLiabilities_PriorYear",
            "COGS", "InterestExpense", "WACC",
        }
        numeric_cols = [c for c in SCORING_COLUMNS if c not in _COMPLETENESS_EXCLUDE]
        n_present = sum(1 for c in numeric_cols if self._is_valid(result.get(c)))
        result["data_completeness"] = n_present / len(numeric_cols) if numeric_cols else 0.0
        result["field_sources"] = field_sources

        # Cache 4 hours
        self._cache.set(cache_key, result, ttl_seconds=14400)
        return result

    def fetch_batch(self, tickers: List[str]) -> pd.DataFrame:
        """Fetch multiple tickers and return a DataFrame indexed by Ticker."""
        from backend.app.services.data_fetcher import SCORING_COLUMNS

        rows: List[Dict[str, Any]] = []
        for i, ticker in enumerate(tickers):
            data = self.fetch_single(ticker)
            data["Ticker"] = ticker
            rows.append(data)
            if i < len(tickers) - 1:
                time.sleep(self._delay)

        if not rows:
            return pd.DataFrame(columns=["Ticker"] + SCORING_COLUMNS)

        df = pd.DataFrame(rows)
        df.set_index("Ticker", inplace=True)
        return df

    def fetch_analyst_ratings(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch analyst ratings -- FMP first, yfinance fallback."""
        # Try FMP consensus targets first
        fmp_targets: Optional[Dict[str, Any]] = None
        try:
            fmp_targets = self._fmp.fetch_analyst_targets(ticker)
        except (FMPQuotaExceeded, FMPHTTPError):
            pass
        except Exception as exc:
            logger.debug(f"FMP fetch_analyst_targets failed for {ticker}: {exc}")

        if fmp_targets:
            # Map to the legacy analyst ratings format
            return {
                "buy": 0,
                "hold": 0,
                "sell": 0,
                "strong_buy": 0,
                "strong_sell": 0,
                "target_low": fmp_targets.get("target_low"),
                "target_mean": fmp_targets.get("target_mean"),
                "target_high": fmp_targets.get("target_high"),
                "target_median": fmp_targets.get("target_median"),
            }

        # Fallback: yfinance
        return self._yf.fetch_analyst_targets(ticker)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid(val: Any) -> bool:
        """True iff val is a finite number."""
        return _is_finite_number(val)

    def _recompute_derived(
        self, result: Dict[str, Any], sources: Dict[str, str]
    ) -> None:
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
            fmp_used = (sources.get("EV") == "fmp" or sources.get("EBITDA") == "fmp")
            sources["EV_EBITDA"] = "fmp" if fmp_used else "yfinance"

        # EV/Sales
        if self._is_valid(ev) and self._is_valid(rev):
            result["EV_Sales"] = _safe_div(ev, rev)
            fmp_used = (sources.get("EV") == "fmp" or sources.get("Revenue") == "fmp")
            sources["EV_Sales"] = "fmp" if fmp_used else "yfinance"

        # P/FCF
        if (self._is_valid(fcf) and fcf > 0 and
                self._is_valid(shares) and shares > 0 and self._is_valid(price)):
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
                fmp_used = any(
                    sources.get(f) == "fmp" for f in ("EBIT", "TotalEquity", "TotalDebt", "Cash")
                )
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
