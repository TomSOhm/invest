"""
Invest Solo -- FMPDataFetcher
Implements the MarketDataSource Protocol against the Financial Modeling Prep API.

Free-tier constraints (hardcoded assumptions):
  - 250 calls/day
  - 5 years of historical data
  - US tickers fully covered; European (Euronext, Frankfurt, Milan) partial

Quota accounting:
  - data/cache/fmp_quota.json persists { "date": "YYYY-MM-DD", "count": int }
  - Counter resets at midnight UTC each day.
  - When count >= settings.fmp_daily_limit, raises FMPQuotaExceeded so the
    HybridDataFetcher falls through to yfinance immediately.

Ticker symbol mapping:
  yfinance uses .PA, .AS, .DE, .SW, .L suffixes.
  FMP free tier understands .PA but differs for others; see _to_fmp_symbol().

Caching (per-endpoint TTLs):
  Annual fundamentals : 24h
  Quarterly           : 6h
  Quotes              : 5 min
  Price history       : 24h
  News                : 1h
  Other               : 6h

Cache keys use the format  fmp:{endpoint_tag}:{original_ticker}
(original ticker, not FMP-mapped, so cache invalidation is consistent).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.config import PROJECT_ROOT, settings
from backend.app.services.cache_service import CacheService

# ---------------------------------------------------------------------------
# Try httpx first, fall back to requests (per spec)
# ---------------------------------------------------------------------------
try:
    import httpx  # type: ignore
    _HTTP_BACKEND = "httpx"
except ImportError:
    import requests as httpx_compat  # type: ignore  # noqa: F401
    _HTTP_BACKEND = "requests"


def _http_get(url: str, timeout: int = 15) -> Any:
    """Issue a GET request and return the parsed JSON body.

    Raises
    ------
    FMPHTTPError
        On non-2xx responses with the status code embedded.
    """
    if _HTTP_BACKEND == "httpx":
        resp = httpx.get(url, timeout=timeout)
    else:
        import requests
        resp = requests.get(url, timeout=timeout)

    if resp.status_code == 404:
        raise FMPHTTPError(404, f"Not Found: {url}")
    if resp.status_code == 401:
        raise FMPHTTPError(401, f"Unauthorized (bad FMP token): {url}")
    if resp.status_code == 403:
        raise FMPHTTPError(403, f"Forbidden / quota exceeded: {url}")
    if resp.status_code == 429:
        raise FMPHTTPError(429, f"Rate limit exceeded: {url}")
    if resp.status_code >= 500:
        raise FMPHTTPError(resp.status_code, f"Server error {resp.status_code}: {url}")
    if resp.status_code >= 400:
        raise FMPHTTPError(resp.status_code, f"Client error {resp.status_code}: {url}")

    return resp.json()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FMPHTTPError(Exception):
    """Wraps an HTTP error from the FMP API."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class FMPQuotaExceeded(Exception):
    """Raised when the daily FMP call budget has been exhausted."""


# ---------------------------------------------------------------------------
# Quota tracker
# ---------------------------------------------------------------------------

QUOTA_FILE = PROJECT_ROOT / "data" / "cache" / "fmp_quota.json"


class _QuotaTracker:
    """Persists a daily call counter to ``fmp_quota.json``.

    The file format is::

        { "date": "YYYY-MM-DD", "count": 42 }

    The counter resets automatically when the stored date differs from today
    (UTC). All mutations are serialised through a single write; on Windows we
    avoid ``fcntl``-based locking and rely on ``os.replace`` for atomicity.
    """

    def __init__(self, path: Path = QUOTA_FILE) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _today(self) -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"date": self._today(), "count": 0}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if data.get("date") != self._today():
                return {"date": self._today(), "count": 0}
            return data
        except (json.JSONDecodeError, OSError):
            return {"date": self._today(), "count": 0}

    def _save(self, data: Dict[str, Any]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self._path)

    def get_count(self) -> int:
        return self._load()["count"]

    def increment(self) -> int:
        """Increment the counter by 1 and return the new value."""
        data = self._load()
        data["count"] += 1
        self._save(data)
        return data["count"]

    def reset(self) -> None:
        """Force-reset the counter to 0 (for testing)."""
        self._save({"date": self._today(), "count": 0})


# ---------------------------------------------------------------------------
# Ticker symbol mapping
# ---------------------------------------------------------------------------

# Known suffix translations yfinance → FMP.
# When FMP returns 404 for a mapped symbol we surface it as "unsupported".
_SUFFIX_MAP: Dict[str, str] = {
    ".AS": ".AMS",   # Euronext Amsterdam
    ".DE": ".F",     # Frankfurt (XETRA)  -- .DEX also tried
    ".SW": ".SW",    # SIX Swiss (same)
    ".L": ".L",      # London (usually same)
    ".MI": ".MI",    # Milan (same)
    ".MC": ".MC",    # Madrid (same)
    # .PA is the same in both -- no mapping needed
}


def _to_fmp_symbol(ticker: str) -> str:
    """Map a yfinance ticker to the best-guess FMP equivalent.

    If the ticker has no recognised exchange suffix or if the suffix is the
    same on FMP (e.g. ``.PA``), the original is returned unchanged.

    Examples
    --------
    >>> _to_fmp_symbol("MC.PA")
    'MC.PA'
    >>> _to_fmp_symbol("ASML.AS")
    'ASML.AMS'
    >>> _to_fmp_symbol("SAP.DE")
    'SAP.F'
    """
    for yf_suffix, fmp_suffix in _SUFFIX_MAP.items():
        if ticker.upper().endswith(yf_suffix.upper()):
            base = ticker[: len(ticker) - len(yf_suffix)]
            return base + fmp_suffix
    return ticker


# ---------------------------------------------------------------------------
# FMPDataFetcher
# ---------------------------------------------------------------------------

class FMPDataFetcher:
    """Implements the MarketDataSource Protocol against the FMP REST API.

    Parameters
    ----------
    token:
        FMP API key. Defaults to the ``FMP_TOKEN`` environment variable.
    cache:
        Shared CacheService instance (reuses the project's existing cache).
    daily_limit:
        Maximum number of FMP calls per day (default from settings.fmp_daily_limit).
    enabled:
        Kill-switch. When False, every method raises FMPQuotaExceeded
        immediately so the hybrid fetcher always falls through to yfinance.
    """

    name: str = "fmp"
    BASE_URL = "https://financialmodelingprep.com/api"

    def __init__(
        self,
        token: Optional[str] = None,
        cache: Optional[CacheService] = None,
        daily_limit: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self._token = token or os.getenv("FMP_TOKEN", "")
        self._cache = cache or CacheService()
        self._quota = _QuotaTracker()
        self._daily_limit = daily_limit if daily_limit is not None else getattr(settings, "fmp_daily_limit", 240)
        self._enabled = enabled if enabled is not None else getattr(settings, "fmp_enabled", True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_quota(self) -> None:
        """Raise FMPQuotaExceeded if the daily budget is exhausted or FMP is disabled."""
        if not self._enabled:
            raise FMPQuotaExceeded("FMP disabled via kill-switch (fmp_enabled=False)")
        if not self._token:
            raise FMPQuotaExceeded("FMP_TOKEN not set -- FMP fetcher disabled")
        if self._quota.get_count() >= self._daily_limit:
            raise FMPQuotaExceeded(
                f"FMP daily quota exhausted ({self._daily_limit} calls/day)"
            )

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Build the FMP URL, check quota, increment counter, fire GET request.

        Raises
        ------
        FMPQuotaExceeded
            When quota exhausted, FMP disabled, or the server returns 403/429.
        FMPHTTPError
            On 401 (bad key) or 5xx errors.
        """
        self._check_quota()

        qs_parts = [f"apikey={self._token}"]
        if params:
            for k, v in params.items():
                qs_parts.append(f"{k}={v}")
        url = f"{self.BASE_URL}{endpoint}?{'&'.join(qs_parts)}"

        self._quota.increment()
        logger.debug(f"FMP GET {endpoint} (quota: {self._quota.get_count()}/{self._daily_limit})")

        try:
            return _http_get(url)
        except FMPHTTPError as exc:
            if exc.status_code in (403, 429):
                logger.warning(f"FMP quota/rate-limit error ({exc.status_code}): {exc}")
                raise FMPQuotaExceeded(str(exc)) from exc
            if exc.status_code == 401:
                logger.error(f"FMP bad API key (401): {exc}")
                raise
            if exc.status_code == 404:
                raise  # caller handles 404 as "ticker unknown to FMP"
            if exc.status_code >= 500:
                # Retry once
                logger.warning(f"FMP server error ({exc.status_code}), retrying once...")
                time.sleep(1)
                return _http_get(url)
            raise

    # ------------------------------------------------------------------
    # Protocol: fetch_quote
    # ------------------------------------------------------------------

    def fetch_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch current market snapshot via ``/v3/quote/{symbol}``."""
        cache_key = f"fmp:quote:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(f"/v3/quote/{fmp_ticker}")
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                logger.debug(f"FMP quote: ticker {ticker} (mapped={fmp_ticker}) not found")
                return {}
            raise

        if not data or not isinstance(data, list) or len(data) == 0:
            return {}

        q = data[0]
        result = {
            "Price": q.get("price", np.nan),
            "MarketCap": q.get("marketCap", np.nan),
            "EV": q.get("enterpriseValue") or np.nan,
            "Shares": q.get("sharesOutstanding", np.nan),
            "Beta": q.get("beta", np.nan),
            "AvgVolume": q.get("avgVolume", np.nan),
            "FiftyTwoWeekHigh": q.get("yearHigh", np.nan),
            "FiftyTwoWeekLow": q.get("yearLow", np.nan),
            "PE": q.get("pe", np.nan),
        }
        # Replace None with NaN
        result = {k: (v if v is not None else np.nan) for k, v in result.items()}
        self._cache.set(cache_key, result, ttl_seconds=300)
        return result

    # ------------------------------------------------------------------
    # Protocol: fetch_fundamentals_annual / quarterly
    # ------------------------------------------------------------------

    def _fetch_statements(self, ticker: str, period: str) -> pd.DataFrame:
        """Fetch income + balance sheet + cash flow and merge into one DataFrame.

        Parameters
        ----------
        period: ``"annual"`` or ``"quarter"``
        """
        fmp_ticker = _to_fmp_symbol(ticker)
        ttl = 86400 if period == "annual" else 21600
        cache_key = f"fmp:fundamentals_{period}:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        endpoints = [
            f"/v3/income-statement/{fmp_ticker}",
            f"/v3/balance-sheet-statement/{fmp_ticker}",
            f"/v3/cash-flow-statement/{fmp_ticker}",
        ]
        frames: List[pd.DataFrame] = []
        for ep in endpoints:
            try:
                data = self._get(ep, params={"period": period, "limit": 5})
            except FMPHTTPError as exc:
                if exc.status_code == 404:
                    logger.debug(f"FMP {ep} 404 for {ticker}")
                    continue
                raise
            if not data or not isinstance(data, list):
                continue
            # Each element is one period's statement; pivot to rows=metrics, cols=dates
            records: Dict[str, Dict[str, Any]] = {}
            for record in data:
                date_str = str(record.get("date", record.get("period", "")))
                for field_name, val in record.items():
                    if field_name in ("date", "symbol", "reportedCurrency",
                                      "cik", "fillingDate", "acceptedDate",
                                      "calendarYear", "period", "link",
                                      "finalLink"):
                        continue
                    if field_name not in records:
                        records[field_name] = {}
                    records[field_name][date_str] = val
            if records:
                frames.append(pd.DataFrame(records).T)

        if not frames:
            return pd.DataFrame()

        merged = pd.concat(frames)
        merged = merged[~merged.index.duplicated(keep="first")]
        self._cache.set(cache_key, merged.to_dict(), ttl_seconds=ttl)
        return merged

    def fetch_fundamentals_annual(self, ticker: str) -> pd.DataFrame:
        """Fetch annual fundamentals via FMP."""
        return self._fetch_statements(ticker, "annual")

    def fetch_fundamentals_quarterly(self, ticker: str) -> pd.DataFrame:
        """Fetch quarterly fundamentals via FMP."""
        return self._fetch_statements(ticker, "quarter")

    # ------------------------------------------------------------------
    # Protocol: fetch_price_history
    # ------------------------------------------------------------------

    def fetch_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """Fetch OHLCV via ``/v3/historical-price-full/{symbol}``."""
        cache_key = f"fmp:price_history:{ticker}:{period}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                df = pd.DataFrame(cached)
                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"])
                return df
            except Exception:
                pass

        # Compute date range from period string
        end_date = datetime.now(tz=timezone.utc).date()
        period_days = {
            "1y": 365, "2y": 730, "3y": 1095, "5y": 1825, "10y": 3650,
        }
        days = period_days.get(period, 1825)
        start_ts = end_date.toordinal() - days
        from datetime import date as _date
        start_date = _date.fromordinal(max(start_ts, _date(2000, 1, 1).toordinal()))

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                f"/v3/historical-price-full/{fmp_ticker}",
                params={"from": start_date.isoformat(), "to": end_date.isoformat()},
            )
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return pd.DataFrame()
            raise

        if not data or "historical" not in data:
            return pd.DataFrame()

        rows = data["historical"]
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if "date" in df.columns:
            df.rename(columns={"date": "Date"}, inplace=True)
            df["Date"] = pd.to_datetime(df["Date"])

        # Normalise column names to match yfinance convention
        col_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }
        df.rename(columns=col_map, inplace=True)

        # Cache 24h
        payload = df.copy()
        if "Date" in payload.columns:
            payload["Date"] = payload["Date"].astype(str)
        self._cache.set(cache_key, payload.to_dict(orient="list"), ttl_seconds=86400)
        return df

    # ------------------------------------------------------------------
    # Protocol: fetch_eps_estimates
    # ------------------------------------------------------------------

    def fetch_eps_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch analyst EPS estimates via ``/v3/analyst-estimates/{symbol}``."""
        cache_key = f"fmp:eps_estimates:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(f"/v3/analyst-estimates/{fmp_ticker}")
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return None
            raise

        if not data or not isinstance(data, list):
            return None

        df = pd.DataFrame(data)
        if df.empty:
            return None

        self._cache.set(cache_key, df.to_dict(), ttl_seconds=21600)
        return df

    # ------------------------------------------------------------------
    # Protocol: fetch_eps_revisions
    # ------------------------------------------------------------------

    def fetch_eps_revisions(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch upgrade/downgrade data as EPS revision proxy.

        Uses ``/v3/upgrades-downgrades/{symbol}`` -- the best free-tier
        approximation for analyst sentiment revisions.
        """
        cache_key = f"fmp:eps_revisions:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(f"/v3/upgrades-downgrades/{fmp_ticker}")
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return None
            raise

        if not data or not isinstance(data, list):
            return None

        df = pd.DataFrame(data)
        if df.empty:
            return None

        self._cache.set(cache_key, df.to_dict(), ttl_seconds=21600)
        return df

    # ------------------------------------------------------------------
    # Protocol: fetch_analyst_targets
    # ------------------------------------------------------------------

    def fetch_analyst_targets(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch consensus price targets via ``/v3/price-target-consensus/{symbol}``."""
        cache_key = f"fmp:analyst_targets:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(f"/v3/price-target-consensus/{fmp_ticker}")
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return None
            raise

        if not data or not isinstance(data, list) or len(data) == 0:
            return None

        item = data[0]
        result: Dict[str, Any] = {
            "target_low": item.get("targetLow"),
            "target_mean": item.get("targetConsensus"),
            "target_high": item.get("targetHigh"),
            "target_median": item.get("targetMedian"),
            "num_analysts": item.get("numberOfAnalysts"),
        }
        self._cache.set(cache_key, result, ttl_seconds=21600)
        return result

    # ------------------------------------------------------------------
    # Protocol: fetch_news
    # ------------------------------------------------------------------

    def fetch_news(self, ticker: str, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        """Fetch news via ``/v3/stock_news?tickers={symbol}&limit={limit}``."""
        cache_key = f"fmp:news:{ticker}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/v3/stock_news",
                params={"tickers": fmp_ticker, "limit": limit},
            )
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return None
            raise

        if not data or not isinstance(data, list):
            return None

        result = [
            {
                "title": item.get("title", ""),
                "publishedAt": item.get("publishedDate", ""),
                "source": item.get("site", ""),
                "url": item.get("url", ""),
            }
            for item in data
        ]
        if not result:
            return None

        self._cache.set(cache_key, result, ttl_seconds=3600)
        return result

    # ------------------------------------------------------------------
    # Protocol: fetch_profile
    # ------------------------------------------------------------------

    def fetch_profile(self, ticker: str) -> Dict[str, Any]:
        """Fetch company profile via ``/v3/profile/{symbol}``."""
        cache_key = f"fmp:profile:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(f"/v3/profile/{fmp_ticker}")
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return {
                    "Name": ticker, "Sector": "", "Industry": "",
                    "Country": "", "Exchange": "", "FirstTradeDate": None,
                }
            raise

        if not data or not isinstance(data, list) or len(data) == 0:
            return {
                "Name": ticker, "Sector": "", "Industry": "",
                "Country": "", "Exchange": "", "FirstTradeDate": None,
            }

        p = data[0]
        result = {
            "Name": p.get("companyName", ticker),
            "Sector": p.get("sector", ""),
            "Industry": p.get("industry", ""),
            "Country": p.get("country", ""),
            "Exchange": p.get("exchangeShortName", ""),
            "FirstTradeDate": p.get("ipoDate"),
        }
        self._cache.set(cache_key, result, ttl_seconds=86400)
        return result

    # ------------------------------------------------------------------
    # Convenience: extract a scoring row from FMP fundamentals
    # ------------------------------------------------------------------

    def extract_scoring_fields(self, ticker: str) -> Dict[str, Any]:
        """Pull the FMP fundamental fields that map directly to SCORING_COLUMNS.

        Returns a partial dict -- only fields FMP can supply. The hybrid
        fetcher fills gaps with yfinance values. All missing values are NaN.

        M4: also extracts prior-year (second-most-recent fiscal column) values
        for the YoY-delta inputs Piotroski needs (ROA_PriorYear,
        OperatingCashflow_PriorYear, LongTermDebt(+_PriorYear),
        CurrentRatio_PriorYear, GrossMargin_PriorYear, Revenue_PriorYear,
        TotalAssets_PriorYear).
        """
        result: Dict[str, Any] = {}
        try:
            ann = self.fetch_fundamentals_annual(ticker)
        except (FMPQuotaExceeded, FMPHTTPError):
            return result

        if ann.empty:
            return result

        # Helper to pull the n-th most-recent value of a FMP field name from
        # the pivoted DataFrame (rows = field names, cols = date strings).  The
        # pivoted layout puts the most recent date first; n=0 -> current, n=1
        # -> prior fiscal year.
        def _nth_finite(fmp_name: str, n: int = 0) -> float:
            if fmp_name not in ann.index:
                return np.nan
            row = ann.loc[fmp_name]
            cols = list(row.index)
            finite_vals: List[float] = []
            for col in cols:
                val = row[col]
                try:
                    fval = float(val)
                    if np.isfinite(fval):
                        finite_vals.append(fval)
                except (TypeError, ValueError):
                    continue
                if len(finite_vals) > n:
                    return finite_vals[n]
            if n < len(finite_vals):
                return finite_vals[n]
            return np.nan

        def _get_field(fmp_name: str, scoring_name: str) -> None:
            v = _nth_finite(fmp_name, n=0)
            if np.isfinite(v):
                result[scoring_name] = v
            else:
                result.setdefault(scoring_name, np.nan)

        def _get_field_prior(fmp_name: str, scoring_name: str) -> None:
            v = _nth_finite(fmp_name, n=1)
            if np.isfinite(v):
                result[scoring_name] = v
            else:
                result.setdefault(scoring_name, np.nan)

        # Income statement
        _get_field("revenue", "Revenue")
        _get_field("ebitda", "EBITDA")
        _get_field("operatingIncome", "EBIT")
        _get_field("netIncome", "NetIncome")
        _get_field("interestExpense", "InterestExpense_FMP")  # raw, used later

        # Balance sheet
        _get_field("totalAssets", "TotalAssets")
        _get_field("totalStockholdersEquity", "TotalEquity")
        _get_field("totalDebt", "TotalDebt")
        _get_field("longTermDebt", "LongTermDebt")
        _get_field("cashAndCashEquivalents", "Cash")
        _get_field("totalCurrentAssets", "CurrentAssets")
        _get_field("totalCurrentLiabilities", "CurrentLiabilities")
        _get_field("retainedEarnings", "RetainedEarnings")

        # Cash flow
        _get_field("operatingCashFlow", "OperatingCashflow")
        _get_field("freeCashFlow", "FCF")
        _get_field("capitalExpenditure", "CapEx")

        # Margins (FMP reports as ratios already)
        _get_field("grossProfitRatio", "GrossMargin")
        _get_field("operatingIncomeRatio", "OperatingMargin")
        _get_field("netIncomeRatio", "NetMargin")

        # Growth (try to compute from last two periods)
        if "Revenue" in result and np.isfinite(result.get("Revenue", np.nan)):
            if "revenue" in ann.index:
                rev_row = ann.loc["revenue"]
                dates = list(rev_row.index)
                if len(dates) >= 2:
                    try:
                        r0 = float(rev_row[dates[0]])  # most recent
                        r1 = float(rev_row[dates[1]])  # year prior
                        if np.isfinite(r0) and np.isfinite(r1) and r1 != 0:
                            result["RevenueGrowth"] = (r0 - r1) / abs(r1)
                    except (TypeError, ValueError):
                        pass

        # Profitability ratios
        _get_field("returnOnEquity", "ROE")
        _get_field("returnOnAssets", "ROA")

        # ------------------------------------------------------------------
        # M4: prior-year inputs for Piotroski Year-over-Year deltas.
        # ------------------------------------------------------------------
        _get_field_prior("revenue", "Revenue_PriorYear")
        _get_field_prior("totalAssets", "TotalAssets_PriorYear")
        _get_field_prior("longTermDebt", "LongTermDebt_PriorYear")
        _get_field_prior("operatingCashFlow", "OperatingCashflow_PriorYear")

        # ROA_PriorYear: derive from NI_prior / TA_prior so it survives even
        # when FMP returns no `returnOnAssets` historical row.
        ni_prior = _nth_finite("netIncome", n=1)
        ta_prior = result.get("TotalAssets_PriorYear", np.nan)
        if (
            np.isfinite(ni_prior)
            and np.isfinite(ta_prior)
            and float(ta_prior) > 0
        ):
            result["ROA_PriorYear"] = float(ni_prior) / float(ta_prior)

        # GrossMargin_PriorYear: prefer FMP's grossProfitRatio prior year if
        # available, else compute from grossProfit_prior / revenue_prior.
        gm_ratio_prior = _nth_finite("grossProfitRatio", n=1)
        if np.isfinite(gm_ratio_prior):
            result["GrossMargin_PriorYear"] = float(gm_ratio_prior)
        else:
            gp_prior = _nth_finite("grossProfit", n=1)
            rev_prior = result.get("Revenue_PriorYear", np.nan)
            if (
                np.isfinite(gp_prior)
                and np.isfinite(rev_prior)
                and float(rev_prior) > 0
            ):
                result["GrossMargin_PriorYear"] = float(gp_prior) / float(rev_prior)

        # CurrentRatio_PriorYear = CA_prior / CL_prior
        ca_prior = _nth_finite("totalCurrentAssets", n=1)
        cl_prior = _nth_finite("totalCurrentLiabilities", n=1)
        if (
            np.isfinite(ca_prior)
            and np.isfinite(cl_prior)
            and float(cl_prior) != 0
        ):
            result["CurrentRatio_PriorYear"] = float(ca_prior) / float(cl_prior)

        return result
