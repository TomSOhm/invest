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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
        return datetime.now(tz=UTC).strftime("%Y-%m-%d")

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"date": self._today(), "count": 0}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if data.get("date") != self._today():
                return {"date": self._today(), "count": 0}
            return data
        except (json.JSONDecodeError, OSError):
            return {"date": self._today(), "count": 0}

    def _save(self, data: dict[str, Any]) -> None:
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
_SUFFIX_MAP: dict[str, str] = {
    ".AS": ".AMS",  # Euronext Amsterdam
    ".DE": ".F",  # Frankfurt (XETRA)  -- .DEX also tried
    ".SW": ".SW",  # SIX Swiss (same)
    ".L": ".L",  # London (usually same)
    ".MI": ".MI",  # Milan (same)
    ".MC": ".MC",  # Madrid (same)
    # .PA is the same in both -- no mapping needed
}

# Non-US exchange suffixes. On the FMP free tier these tickers return 402
# "Premium Query Parameter: Special Endpoint" -- the symbol set is gated to
# paid plans. We short-circuit the FMP fetcher for them so we don't waste
# quota or pollute the dashboard with 100%-bad-request noise. Hybrid fetcher
# catches FMPQuotaExceeded and routes those tickers straight to yfinance.
_NON_US_SUFFIXES: frozenset[str] = frozenset({
    ".PA",  # Paris (Euronext)
    ".AS",  # Amsterdam
    ".AMS",  # Amsterdam (FMP mapped form)
    ".BR",  # Brussels
    ".LS",  # Lisbon
    ".DE",  # Frankfurt (XETRA)
    ".F",  # Frankfurt floor
    ".MI",  # Milan
    ".MC",  # Madrid
    ".SW",  # SIX Swiss
    ".L",  # London (LSE)
    ".ST",  # Stockholm
    ".CO",  # Copenhagen
    ".HE",  # Helsinki
    ".OL",  # Oslo
    ".VI",  # Vienna
    ".IR",  # Dublin
    ".WA",  # Warsaw
    ".PR",  # Prague
    ".AT",  # Athens
    ".T",  # Tokyo
    ".HK",  # Hong Kong
    ".SS",  # Shanghai
    ".SZ",  # Shenzhen
    ".AX",  # Sydney (ASX)
    ".TO",  # Toronto (TSX)
    ".V",  # Vancouver (TSX-V)
})


def _is_us_ticker(ticker: str) -> bool:
    """True iff ticker has no recognised non-US exchange suffix.

    FMP free tier (Basic plan) serves only the US sample universe; every
    non-US ticker returns 402 Premium. Multi-class US tickers like 'BRK.B'
    correctly stay True because '.B' is not in _NON_US_SUFFIXES.
    """
    if "." not in ticker:
        return True
    suffix = "." + ticker.rsplit(".", 1)[1].upper()
    return suffix not in _NON_US_SUFFIXES


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
    # FMP deprecated /api/v3/* for new free-tier accounts (post-2025-08-31).
    # /stable/* is the current path-versioned namespace and accepts symbol as
    # a query param instead of in the URL path.
    BASE_URL = "https://financialmodelingprep.com/stable"

    def __init__(
        self,
        token: str | None = None,
        cache: CacheService | None = None,
        daily_limit: int | None = None,
        enabled: bool | None = None,
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
            raise FMPQuotaExceeded(f"FMP daily quota exhausted ({self._daily_limit} calls/day)")

    def _skip_if_non_us(self, ticker: str) -> None:
        """Short-circuit non-US tickers: free FMP only serves the US sample universe.

        Avoids burning the daily quota + cluttering the FMP dashboard with
        100%-bad-request noise on EU/PEA tickers that always 402. The hybrid
        fetcher catches FMPQuotaExceeded and falls through to yfinance.
        """
        if not _is_us_ticker(ticker):
            raise FMPQuotaExceeded(f"FMP free tier does not cover non-US ticker {ticker}")

    def _cached_402(self, ticker: str, endpoint: str) -> bool:
        """Has this (ticker, endpoint) pair already returned 402 today? (defense-in-depth)."""
        return self._cache.get(f"fmp:402:{ticker}:{endpoint}") is not None

    def _mark_402(self, ticker: str, endpoint: str) -> None:
        """Remember a 402 verdict for 24h so we don't retry it."""
        self._cache.set(f"fmp:402:{ticker}:{endpoint}", {"402": True}, ttl_seconds=86400)

    def _get(self, endpoint: str, params: dict[str, Any] | None = None, ticker: str | None = None) -> Any:
        """Build the FMP URL, check quota, increment counter, fire GET request.

        Parameters
        ----------
        ticker : optional
            When provided, enables per-(ticker, endpoint) 402 caching so a
            single subscription-gate failure isn't re-fired on every refresh
            within the same day.

        Raises
        ------
        FMPQuotaExceeded
            When quota exhausted, FMP disabled, the server returns 403/429/402,
            or a prior 402 verdict for this (ticker, endpoint) is still cached.
        FMPHTTPError
            On 401 (bad key) or 5xx errors.
        """
        self._check_quota()

        # 402 short-circuit: if we've already learned this (ticker, endpoint)
        # combo is paywalled, don't even hit the network.
        if ticker is not None and self._cached_402(ticker, endpoint):
            raise FMPQuotaExceeded(f"cached 402 for {ticker} {endpoint}")

        qs_parts = [f"apikey={self._token}"]
        if params:
            for k, v in params.items():
                qs_parts.append(f"{k}={v}")
        url = f"{self.BASE_URL}{endpoint}?{'&'.join(qs_parts)}"

        logger.debug(f"FMP GET {endpoint} (quota: {self._quota.get_count()}/{self._daily_limit})")

        try:
            result = _http_get(url)
            # Only count successful calls toward the quota -- 4xx errors that
            # mean "not for you" (legacy endpoint, paid plan only) don't consume
            # FMP's server-side quota, so we shouldn't burn our own counter.
            self._quota.increment()
            return result
        except FMPHTTPError as exc:
            if exc.status_code in (403, 429):
                logger.warning(f"FMP quota/rate-limit error ({exc.status_code}): {exc}")
                raise FMPQuotaExceeded(str(exc)) from exc
            if exc.status_code == 402:
                # Endpoint or symbol requires a paid plan (e.g. /news/stock,
                # or EU tickers on free tier). Cache the verdict so we don't
                # retry it for 24h. Treat like a quota miss so the hybrid
                # fetcher falls through to the other source without spamming
                # the log on every call.
                logger.info(f"FMP endpoint requires paid plan (402): {endpoint} ticker={ticker}")
                if ticker is not None:
                    self._mark_402(ticker, endpoint)
                raise FMPQuotaExceeded(f"402 paid-plan-only: {endpoint}") from exc
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

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch current market snapshot via ``/stable/quote?symbol={symbol}``."""
        self._skip_if_non_us(ticker)
        cache_key = f"fmp:quote:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get("/quote", params={"symbol": fmp_ticker}, ticker=ticker)
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                logger.debug(f"FMP quote: ticker {ticker} (mapped={fmp_ticker}) not found")
                return {}
            raise

        if not data or not isinstance(data, list) or len(data) == 0:
            return {}

        q = data[0]

        # /stable/quote on free tier is slimmer than the legacy /v3/quote:
        # it carries Price, MarketCap, yearHigh, yearLow, change, volume.
        # Beta, EV, Shares, AvgVolume, PE are gated to paid endpoints
        # (/stable/profile, /stable/ratios-ttm). We leave them NaN here and
        # let HybridDataFetcher fall through to yfinance for those fields --
        # saves two FMP calls per ticker per refresh.
        result = {
            "Price": q.get("price", np.nan),
            "MarketCap": q.get("marketCap", np.nan),
            "EV": np.nan,
            "Shares": np.nan,
            "Beta": np.nan,
            "AvgVolume": np.nan,
            "FiftyTwoWeekHigh": q.get("yearHigh", np.nan),
            "FiftyTwoWeekLow": q.get("yearLow", np.nan),
            "PE": np.nan,
        }
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
        self._skip_if_non_us(ticker)
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
            "/income-statement",
            "/balance-sheet-statement",
            "/cash-flow-statement",
        ]
        frames: list[pd.DataFrame] = []
        for ep in endpoints:
            try:
                data = self._get(
                    ep,
                    params={"symbol": fmp_ticker, "period": period, "limit": 5},
                    ticker=ticker,
                )
            except FMPHTTPError as exc:
                if exc.status_code == 404:
                    logger.debug(f"FMP {ep} 404 for {ticker}")
                    continue
                raise
            if not data or not isinstance(data, list):
                continue
            # Each element is one period's statement; pivot to rows=metrics, cols=dates
            records: dict[str, dict[str, Any]] = {}
            for record in data:
                date_str = str(record.get("date", record.get("period", "")))
                for field_name, val in record.items():
                    if field_name in (
                        "date",
                        "symbol",
                        "reportedCurrency",
                        "cik",
                        "fillingDate",
                        "acceptedDate",
                        "calendarYear",
                        "period",
                        "link",
                        "finalLink",
                    ):
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
        """Fetch OHLCV via ``/stable/historical-price-eod/full?symbol={symbol}``."""
        self._skip_if_non_us(ticker)
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
        end_date = datetime.now(tz=UTC).date()
        period_days = {
            "1y": 365,
            "2y": 730,
            "3y": 1095,
            "5y": 1825,
            "10y": 3650,
        }
        days = period_days.get(period, 1825)
        start_ts = end_date.toordinal() - days
        from datetime import date as _date

        start_date = _date.fromordinal(max(start_ts, _date(2000, 1, 1).toordinal()))

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/historical-price-eod/full",
                params={
                    "symbol": fmp_ticker,
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
                ticker=ticker,
            )
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return pd.DataFrame()
            raise

        # /stable/historical-price-eod/full returns a flat list of OHLCV rows
        # (no "historical" wrapper key like the legacy /v3 endpoint).
        if isinstance(data, dict) and "historical" in data:
            rows = data["historical"]  # legacy shape, kept for safety
        elif isinstance(data, list):
            rows = data
        else:
            return pd.DataFrame()
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if "date" in df.columns:
            df.rename(columns={"date": "Date"}, inplace=True)
            df["Date"] = pd.to_datetime(df["Date"])

        # Normalise column names to match yfinance convention
        col_map = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
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

    def fetch_eps_estimates(self, ticker: str) -> pd.DataFrame | None:
        """Fetch analyst EPS estimates via ``/stable/analyst-estimates?symbol={symbol}``."""
        self._skip_if_non_us(ticker)
        cache_key = f"fmp:eps_estimates:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/analyst-estimates",
                params={"symbol": fmp_ticker, "period": "annual", "limit": 10},
                ticker=ticker,
            )
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

    def fetch_eps_revisions(self, ticker: str) -> pd.DataFrame | None:
        """Fetch analyst grade history as EPS revision proxy.

        Uses ``/stable/grades-historical?symbol={symbol}`` -- the current
        free-tier replacement for the legacy /v3/upgrades-downgrades endpoint.
        """
        self._skip_if_non_us(ticker)
        cache_key = f"fmp:eps_revisions:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/grades-historical",
                params={"symbol": fmp_ticker, "limit": 50},
                ticker=ticker,
            )
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

    def fetch_analyst_targets(self, ticker: str) -> dict[str, Any] | None:
        """Fetch consensus price targets via ``/stable/price-target-consensus?symbol={symbol}``."""
        self._skip_if_non_us(ticker)
        cache_key = f"fmp:analyst_targets:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/price-target-consensus",
                params={"symbol": fmp_ticker},
                ticker=ticker,
            )
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return None
            raise

        if not data or not isinstance(data, list) or len(data) == 0:
            return None

        item = data[0]
        result: dict[str, Any] = {
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

    def fetch_news(self, ticker: str, limit: int = 20) -> list[dict[str, Any]] | None:
        """Fetch news via ``/stable/news/stock?symbols={symbol}&limit={limit}``.

        Note: the news endpoint requires a paid FMP plan. On free tier this
        raises FMPQuotaExceeded (402 → mapped) and the hybrid fetcher falls
        back to yfinance news.
        """
        self._skip_if_non_us(ticker)
        cache_key = f"fmp:news:{ticker}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/news/stock",
                params={"symbols": fmp_ticker, "limit": limit},
                ticker=ticker,
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
                # M9: sentiment module reads `text` first; fall back to title content.
                "text": item.get("text", "") or item.get("title", ""),
                # Keep both `publishedAt` (M2 contract) and `published_date` (M9 spec).
                "publishedAt": item.get("publishedDate", ""),
                "published_date": item.get("publishedDate", ""),
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

    def fetch_profile(self, ticker: str) -> dict[str, Any]:
        """Fetch company profile via ``/stable/profile?symbol={symbol}``."""
        self._skip_if_non_us(ticker)
        cache_key = f"fmp:profile:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        fmp_ticker = _to_fmp_symbol(ticker)
        try:
            data = self._get(
                "/profile",
                params={"symbol": fmp_ticker},
                ticker=ticker,
            )
        except FMPHTTPError as exc:
            if exc.status_code == 404:
                return {
                    "Name": ticker,
                    "Sector": "",
                    "Industry": "",
                    "Country": "",
                    "Exchange": "",
                    "FirstTradeDate": None,
                }
            raise

        if not data or not isinstance(data, list) or len(data) == 0:
            return {
                "Name": ticker,
                "Sector": "",
                "Industry": "",
                "Country": "",
                "Exchange": "",
                "FirstTradeDate": None,
            }

        p = data[0]
        result = {
            "Name": p.get("companyName", ticker),
            "Sector": p.get("sector", ""),
            "Industry": p.get("industry", ""),
            "Country": p.get("country", ""),
            # /stable/profile renamed exchangeShortName -> exchange. Fall back to
            # the full name if exchange is empty.
            "Exchange": p.get("exchange", "") or p.get("exchangeFullName", ""),
            "FirstTradeDate": p.get("ipoDate"),
        }
        self._cache.set(cache_key, result, ttl_seconds=86400)
        return result

    # ------------------------------------------------------------------
    # Convenience: extract a scoring row from FMP fundamentals
    # ------------------------------------------------------------------

    def extract_scoring_fields(self, ticker: str) -> dict[str, Any]:
        """Pull the FMP fundamental fields that map directly to SCORING_COLUMNS.

        Returns a partial dict -- only fields FMP can supply. The hybrid
        fetcher fills gaps with yfinance values. All missing values are NaN.

        M4: also extracts prior-year (second-most-recent fiscal column) values
        for the YoY-delta inputs Piotroski needs (ROA_PriorYear,
        OperatingCashflow_PriorYear, LongTermDebt(+_PriorYear),
        CurrentRatio_PriorYear, GrossMargin_PriorYear, Revenue_PriorYear,
        TotalAssets_PriorYear).
        """
        result: dict[str, Any] = {}
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
            finite_vals: list[float] = []
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
        if np.isfinite(ni_prior) and np.isfinite(ta_prior) and float(ta_prior) > 0:
            result["ROA_PriorYear"] = float(ni_prior) / float(ta_prior)

        # GrossMargin_PriorYear: prefer FMP's grossProfitRatio prior year,
        # else compute from grossProfit_prior / revenue_prior.
        gm_ratio_prior = _nth_finite("grossProfitRatio", n=1)
        if np.isfinite(gm_ratio_prior):
            result["GrossMargin_PriorYear"] = float(gm_ratio_prior)
        else:
            gp_prior = _nth_finite("grossProfit", n=1)
            rev_prior = result.get("Revenue_PriorYear", np.nan)
            if np.isfinite(gp_prior) and np.isfinite(rev_prior) and float(rev_prior) > 0:
                result["GrossMargin_PriorYear"] = float(gp_prior) / float(rev_prior)

        # CurrentRatio_PriorYear = CA_prior / CL_prior
        ca_prior = _nth_finite("totalCurrentAssets", n=1)
        cl_prior = _nth_finite("totalCurrentLiabilities", n=1)
        if np.isfinite(ca_prior) and np.isfinite(cl_prior) and float(cl_prior) != 0:
            result["CurrentRatio_PriorYear"] = float(ca_prior) / float(cl_prior)

        # ------------------------------------------------------------------
        # M5: Beneish M-Score prior-year scalars + balance-sheet add-ons.
        # ------------------------------------------------------------------
        _get_field_prior("totalCurrentAssets", "CurrentAssets_PriorYear")
        _get_field_prior("totalCurrentLiabilities", "CurrentLiabilities_PriorYear")
        _get_field("netReceivables", "Receivables")
        _get_field_prior("netReceivables", "Receivables_PriorYear")
        _get_field("propertyPlantEquipmentNet", "PPE")
        _get_field_prior("propertyPlantEquipmentNet", "PPE_PriorYear")
        _get_field("depreciationAndAmortization", "DepreciationAmortization")
        _get_field_prior("depreciationAndAmortization", "DepreciationAmortization_PriorYear")
        _get_field("sellingGeneralAndAdministrativeExpenses", "SGA")
        _get_field_prior("sellingGeneralAndAdministrativeExpenses", "SGA_PriorYear")
        _get_field("costOfRevenue", "COGS")
        _get_field("interestExpense", "InterestExpense")

        # ------------------------------------------------------------------
        # M5: 5y / 3y history arrays for Moat + Earnings Quality modules
        # ------------------------------------------------------------------
        def _get_history(fmp_name: str, n: int) -> list[float]:
            """Extract the n most-recent finite values for fmp_name."""
            if fmp_name not in ann.index:
                return []
            row = ann.loc[fmp_name]
            out: list[float] = []
            for col in list(row.index)[:n]:
                try:
                    fval = float(row[col])
                    if np.isfinite(fval):
                        out.append(fval)
                except (TypeError, ValueError):
                    continue
            return out

        result["FCF_History_5y"] = _get_history("freeCashFlow", 5)
        result["NetIncome_History_5y"] = _get_history("netIncome", 5)
        result["OperatingMargin_History_5y"] = _get_history("operatingIncomeRatio", 5)

        # ROIC history: derive from operatingIncome and (equity + debt - cash) per year.
        roic_hist: list[float] = []
        ic_hist: list[float] = []
        ebit_hist: list[float] = []
        if "operatingIncome" in ann.index:
            opi = ann.loc["operatingIncome"]
            eq = ann.loc["totalStockholdersEquity"] if "totalStockholdersEquity" in ann.index else None
            debt = ann.loc["totalDebt"] if "totalDebt" in ann.index else None
            cash = ann.loc["cashAndCashEquivalents"] if "cashAndCashEquivalents" in ann.index else None
            cols = list(opi.index)
            for col in cols[:5]:
                try:
                    e = float(opi[col]) if col in opi.index else float("nan")
                    eq_v = float(eq[col]) if eq is not None and col in eq.index else float("nan")
                    d_v = float(debt[col]) if debt is not None and col in debt.index else float("nan")
                    c_v = float(cash[col]) if cash is not None and col in cash.index else float("nan")
                    if all(np.isfinite(x) for x in (e, eq_v, d_v, c_v)):
                        invested = eq_v + d_v - c_v
                        if invested > 0:
                            roic_hist.append((e * 0.75) / invested)
                            ic_hist.append(invested)
                        if np.isfinite(e):
                            ebit_hist.append(e)
                except (TypeError, ValueError):
                    continue
        result["ROIC_History_5y"] = roic_hist
        result["EBIT_History_3y"] = ebit_hist[:3]
        result["InvestedCapital_History_3y"] = ic_hist[:3]

        return result
