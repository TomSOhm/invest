"""
Invest Solo -- YFinanceDataFetcher
Wraps all yfinance calls and exposes the MarketDataSource Protocol surface.

The heavy helper functions (_latest_from_statement, _get_real_ebit, etc.) are
lifted directly from M1's data_fetcher.py to avoid duplication.  data_fetcher.py
is kept as a compatibility shim over HybridDataFetcher and no longer contains
the yfinance plumbing directly; this module owns it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from backend.app.services.cache_service import CacheService

# ---------------------------------------------------------------------------
# Low-level helpers (moved from data_fetcher.py)
# ---------------------------------------------------------------------------


def _safe_get(info: dict[str, Any], key: str, default: Any = np.nan) -> Any:
    """Safely extract a value from a yfinance info dict."""
    val = info.get(key, default)
    if val is None:
        return default
    return val


def _safe_div(numerator: Any, denominator: Any) -> float:
    """Safe division returning NaN on division-by-zero or invalid inputs."""
    try:
        if denominator is None or denominator == 0 or np.isnan(denominator):
            return np.nan
        if numerator is None or np.isnan(numerator):
            return np.nan
        return float(numerator) / float(denominator)
    except (TypeError, ValueError):
        return np.nan


def _is_finite_number(val: Any) -> bool:
    """True iff val is a finite numeric (rejects None, NaN, Inf, non-numeric)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    return np.isfinite(f)


def _safe_float(val: Any) -> float | None:
    """Coerce a value to ``float`` or ``None`` for non-finite/non-numeric inputs."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return f


def _latest_from_statement(
    statement: pd.DataFrame | None,
    candidate_keys: Sequence[str],
) -> float:
    """Pull the most-recent value of any candidate row label from a yfinance statement.

    yfinance statements (``tk.financials``, ``tk.balance_sheet``, ``tk.cashflow``)
    are DataFrames where rows are line items and columns are period-end dates with
    the most recent first. We probe ``candidate_keys`` in order and return the
    first non-NaN, non-zero value from the most-recent column. Returns NaN if
    nothing is found. Never raises.
    """
    return _nth_from_statement(statement, candidate_keys, n=0)


def _nth_from_statement(
    statement: pd.DataFrame | None,
    candidate_keys: Sequence[str],
    n: int = 0,
) -> float:
    """Like :func:`_latest_from_statement` but reads the *n*-th most-recent column.

    ``n=0`` -> most recent (current fiscal year)
    ``n=1`` -> second-most-recent (prior fiscal year)
    Returns NaN if the statement has fewer than ``n+1`` columns or none of the
    candidate keys exist.  Used by M4 to populate ``*_PriorYear`` fields.
    """
    if statement is None or not isinstance(statement, pd.DataFrame) or statement.empty:
        return np.nan
    cols = list(statement.columns)
    if n >= len(cols):
        return np.nan
    target_col = cols[n]
    for key in candidate_keys:
        if key not in statement.index:
            continue
        try:
            row = statement.loc[key]
        except KeyError:
            continue
        if isinstance(row, pd.DataFrame):
            if row.empty:
                continue
            row = row.iloc[0]
        if target_col not in row.index:
            continue
        val = row[target_col]
        if _is_finite_number(val) and float(val) != 0:
            return float(val)
    return np.nan


def _get_real_ebit(
    tk: yf.Ticker,
    info: dict[str, Any],
    ebitda: float,
    cashflow: pd.DataFrame | None = None,
    financials: pd.DataFrame | None = None,
) -> float:
    """Fetch real EBIT, never aliasing to EBITDA.

    Priority:
        1. ``tk.financials.loc["EBIT"]`` (most recent column)
        2. ``tk.financials.loc["Operating Income"]`` / ``OperatingIncome``
        3. Fallback: ``EBITDA - D&A`` where D&A comes from cashflow
        4. NaN
    """
    try:
        if financials is None:
            financials = tk.financials
    except Exception as exc:
        logger.debug(f"financials access failed: {exc}")
        financials = None

    ebit = _latest_from_statement(
        financials,
        ["EBIT", "Operating Income", "OperatingIncome", "Total Operating Income As Reported"],
    )
    if _is_finite_number(ebit):
        return ebit

    if not _is_finite_number(ebitda):
        return np.nan
    try:
        if cashflow is None:
            cashflow = tk.cashflow
    except Exception as exc:
        logger.debug(f"cashflow access failed: {exc}")
        cashflow = None

    da = _latest_from_statement(
        cashflow,
        [
            "Depreciation And Amortization",
            "Depreciation",
            "Depreciation Amortization Depletion",
            "DepreciationAndAmortization",
        ],
    )
    if _is_finite_number(da) and da > 0:
        return float(ebitda) - float(da)
    return np.nan


def _get_real_interest_expense(
    tk: yf.Ticker,
    financials: pd.DataFrame | None = None,
) -> float:
    """Fetch real Interest Expense from the income statement.

    Returns a POSITIVE value (expense convention normalised). Returns NaN if not
    available -- never fabricates.
    """
    try:
        if financials is None:
            financials = tk.financials
    except Exception as exc:
        logger.debug(f"financials access failed for interest: {exc}")
        return np.nan

    val = _latest_from_statement(
        financials,
        [
            "Interest Expense",
            "InterestExpense",
            "Interest Expense Non Operating",
            "Net Non Operating Interest Income Expense",
            "Interest Expense, Net",
        ],
    )
    if not _is_finite_number(val):
        return np.nan
    return abs(float(val))


def _get_shares_prior_year(tk: yf.Ticker) -> float:
    """Get shares outstanding ~1 year ago via ``tk.get_shares_full()``.

    Returns NaN if the API returns nothing or fails.
    """
    try:
        s = tk.get_shares_full()
    except Exception as exc:
        logger.debug(f"get_shares_full failed: {exc}")
        return np.nan
    if s is None or len(s) == 0:
        return np.nan
    try:
        s = s.dropna()
        if s.empty:
            return np.nan
        idx = pd.to_datetime(s.index, utc=True, errors="coerce")
        idx = pd.DatetimeIndex(idx)
        if idx.isna().all():
            return float(s.iloc[0])
        latest_ts = idx.max()
        target_ts = latest_ts - pd.Timedelta(days=365)
        mask = idx <= target_ts
        mask_arr = np.asarray(mask)
        if mask_arr.any():
            sub = s.iloc[np.flatnonzero(mask_arr)]
            if not sub.empty:
                return float(sub.iloc[-1])
        return float(s.iloc[0])
    except Exception as exc:
        logger.debug(f"shares prior year extraction failed: {exc}")
        return np.nan


def _get_balance_sheet_items(
    tk: yf.Ticker,
    balance_sheet: pd.DataFrame | None = None,
) -> dict[str, float]:
    """Fetch CurrentAssets, CurrentLiabilities, RetainedEarnings + equity/asset backups."""
    try:
        if balance_sheet is None:
            balance_sheet = tk.balance_sheet
    except Exception as exc:
        logger.debug(f"balance_sheet access failed: {exc}")
        balance_sheet = None

    return {
        "CurrentAssets": _latest_from_statement(
            balance_sheet,
            ["Current Assets", "Total Current Assets", "CurrentAssets"],
        ),
        "CurrentLiabilities": _latest_from_statement(
            balance_sheet,
            ["Current Liabilities", "Total Current Liabilities", "CurrentLiabilities"],
        ),
        "RetainedEarnings": _latest_from_statement(
            balance_sheet,
            ["Retained Earnings", "RetainedEarnings"],
        ),
        "TotalAssets_BS": _latest_from_statement(
            balance_sheet,
            ["Total Assets", "TotalAssets"],
        ),
        "TotalEquity_BS": _latest_from_statement(
            balance_sheet,
            [
                "Stockholders Equity",
                "Total Stockholder Equity",
                "TotalStockholderEquity",
                "Common Stock Equity",
            ],
        ),
    }


# ---------------------------------------------------------------------------
# M4 -- Year-over-Year (prior-year) extractor for Piotroski deltas
# ---------------------------------------------------------------------------

# yfinance row labels for line items we need YoY pairs for.
_LTD_KEYS = (
    "Long Term Debt",
    "LongTermDebt",
    "Long Term Debt And Capital Lease Obligation",
    "Long Term Debt Noncurrent",
)
_TA_KEYS = ("Total Assets", "TotalAssets")
_REV_KEYS = (
    "Total Revenue",
    "TotalRevenue",
    "Revenue",
    "Operating Revenue",
)
_NI_KEYS = (
    "Net Income",
    "NetIncome",
    "Net Income Common Stockholders",
    "Net Income Continuous Operations",
)
_CFO_KEYS = (
    "Operating Cash Flow",
    "Cash Flow From Continuing Operating Activities",
    "Total Cash From Operating Activities",
    "OperatingCashFlow",
)
_GP_KEYS = (
    "Gross Profit",
    "GrossProfit",
)
_CA_KEYS = ("Current Assets", "Total Current Assets", "CurrentAssets")
_CL_KEYS = ("Current Liabilities", "Total Current Liabilities", "CurrentLiabilities")


def _get_yoy_inputs(
    balance_sheet: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
) -> dict[str, float]:
    """Pull prior-year (n=1 column) values needed for Piotroski YoY deltas.

    Returns a dict with the M4 ``*_PriorYear`` fields plus ``LongTermDebt`` and
    ``LongTermDebt_PriorYear``.  Missing values are NaN.

    Note
    ----
    Each value is fetched from the second-most-recent column of the relevant
    yfinance statement.  When the source has fewer than 2 historical periods
    (very common for European mid-caps on the free tier), values are NaN and
    the corresponding Piotroski signals will simply be skipped.
    """
    out: dict[str, float] = {}

    # Balance sheet ------------------------------------------------------
    out["LongTermDebt"] = _nth_from_statement(balance_sheet, _LTD_KEYS, n=0)
    out["LongTermDebt_PriorYear"] = _nth_from_statement(balance_sheet, _LTD_KEYS, n=1)
    out["TotalAssets_PriorYear"] = _nth_from_statement(balance_sheet, _TA_KEYS, n=1)
    ca_prior = _nth_from_statement(balance_sheet, _CA_KEYS, n=1)
    cl_prior = _nth_from_statement(balance_sheet, _CL_KEYS, n=1)
    if _is_finite_number(ca_prior) and _is_finite_number(cl_prior) and float(cl_prior) != 0:
        out["CurrentRatio_PriorYear"] = float(ca_prior) / float(cl_prior)
    else:
        out["CurrentRatio_PriorYear"] = np.nan

    # Income statement ---------------------------------------------------
    rev_prior = _nth_from_statement(financials, _REV_KEYS, n=1)
    ni_prior = _nth_from_statement(financials, _NI_KEYS, n=1)
    gp_prior = _nth_from_statement(financials, _GP_KEYS, n=1)
    out["Revenue_PriorYear"] = rev_prior
    if _is_finite_number(gp_prior) and _is_finite_number(rev_prior) and float(rev_prior) > 0:
        out["GrossMargin_PriorYear"] = float(gp_prior) / float(rev_prior)
    else:
        out["GrossMargin_PriorYear"] = np.nan

    # ROA prior year = NI_prior / TotalAssets_prior (real, not approximated)
    if (
        _is_finite_number(ni_prior)
        and _is_finite_number(out["TotalAssets_PriorYear"])
        and float(out["TotalAssets_PriorYear"]) > 0
    ):
        out["ROA_PriorYear"] = float(ni_prior) / float(out["TotalAssets_PriorYear"])
    else:
        out["ROA_PriorYear"] = np.nan

    # Cash flow ----------------------------------------------------------
    out["OperatingCashflow_PriorYear"] = _nth_from_statement(cashflow, _CFO_KEYS, n=1)

    return out


def _years_since_first_trade(info: dict[str, Any]) -> float:
    """Compute years since first listing from ``firstTradeDateEpochUtc``."""
    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is None or not _is_finite_number(epoch):
        return np.nan
    try:
        first_trade = datetime.fromtimestamp(float(epoch), tz=UTC)
        now = datetime.now(tz=UTC)
        return (now - first_trade).days / 365.25
    except (OverflowError, OSError, ValueError):
        return np.nan


@staticmethod
def _country_to_code(country_name: str) -> str:
    """Map a country name to its ISO 2-letter code."""
    if not country_name:
        return ""
    mapping = {
        "france": "FR",
        "germany": "DE",
        "netherlands": "NL",
        "belgium": "BE",
        "italy": "IT",
        "spain": "ES",
        "portugal": "PT",
        "ireland": "IE",
        "austria": "AT",
        "finland": "FI",
        "sweden": "SE",
        "denmark": "DK",
        "norway": "NO",
        "poland": "PL",
        "luxembourg": "LU",
        "greece": "GR",
        "united states": "US",
        "united kingdom": "GB",
        "switzerland": "CH",
        "japan": "JP",
        "china": "CN",
        "canada": "CA",
        "australia": "AU",
        "south korea": "KR",
        "brazil": "BR",
        "india": "IN",
        "taiwan": "TW",
        "hong kong": "HK",
        "singapore": "SG",
        "mexico": "MX",
    }
    normalized = country_name.strip().lower()
    code = mapping.get(normalized, "")
    if not code:
        if len(country_name.strip()) == 2:
            return country_name.strip().upper()
    return code


# ---------------------------------------------------------------------------
# YFinanceDataFetcher
# ---------------------------------------------------------------------------


class YFinanceDataFetcher:
    """Implements the MarketDataSource Protocol via yfinance.

    All M1-proven yfinance plumbing lives here. The legacy DataFetcher
    (data_fetcher.py) delegates to HybridDataFetcher which uses this class.
    """

    name: str = "yfinance"

    def __init__(self, cache: CacheService | None = None) -> None:
        self._cache = cache or CacheService()

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Fetch current price snapshot from yfinance info dict."""
        cache_key = f"yf:quote:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            result = {
                "Price": _safe_get(info, "currentPrice", _safe_get(info, "regularMarketPrice", np.nan)),
                "MarketCap": _safe_get(info, "marketCap", np.nan),
                "EV": _safe_get(info, "enterpriseValue", np.nan),
                "Shares": _safe_get(info, "sharesOutstanding", np.nan),
                "Beta": _safe_get(info, "beta", np.nan),
                "AvgVolume": _safe_get(info, "averageDailyVolume3Month", np.nan),
                "FiftyTwoWeekHigh": _safe_get(info, "fiftyTwoWeekHigh", np.nan),
                "FiftyTwoWeekLow": _safe_get(info, "fiftyTwoWeekLow", np.nan),
                "ForwardPE": _safe_get(info, "forwardPE", np.nan),
                "PEG": _safe_get(info, "pegRatio", np.nan),
            }
            # Short TTL for quote data (5 minutes)
            self._cache.set(cache_key, result, ttl_seconds=300)
            return result
        except Exception as exc:
            logger.warning(f"yfinance fetch_quote failed for {ticker}: {exc}")
            return {}

    def fetch_fundamentals_annual(self, ticker: str) -> pd.DataFrame:
        """Fetch and merge annual income + balance sheet + cashflow statements."""
        cache_key = f"yf:fundamentals_annual:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            # Reconstruct DataFrame from cached dict
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        try:
            tk = yf.Ticker(ticker)
            frames = []
            for attr_name in ("financials", "balance_sheet", "cashflow"):
                try:
                    df = getattr(tk, attr_name)
                    if df is not None and not df.empty:
                        frames.append(df)
                except Exception as exc:
                    logger.debug(f"{ticker}: {attr_name} access failed: {exc}")

            if not frames:
                return pd.DataFrame()

            merged = pd.concat(frames)
            # Remove duplicate index entries (keep first occurrence)
            merged = merged[~merged.index.duplicated(keep="first")]
            # Normalise columns to ISO date strings
            merged.columns = [c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c) for c in merged.columns]
            # Cache for 24 hours
            self._cache.set(cache_key, merged.to_dict(), ttl_seconds=86400)
            return merged
        except Exception as exc:
            logger.warning(f"yfinance fetch_fundamentals_annual failed for {ticker}: {exc}")
            return pd.DataFrame()

    def fetch_fundamentals_quarterly(self, ticker: str) -> pd.DataFrame:
        """Fetch and merge quarterly income + balance sheet + cashflow statements."""
        cache_key = f"yf:fundamentals_quarterly:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return pd.DataFrame(cached)
            except Exception:
                pass

        try:
            tk = yf.Ticker(ticker)
            frames = []
            for attr_name in (
                "quarterly_financials",
                "quarterly_balance_sheet",
                "quarterly_cashflow",
            ):
                try:
                    df = getattr(tk, attr_name)
                    if df is not None and not df.empty:
                        frames.append(df)
                except Exception as exc:
                    logger.debug(f"{ticker}: {attr_name} access failed: {exc}")

            if not frames:
                return pd.DataFrame()

            merged = pd.concat(frames)
            merged = merged[~merged.index.duplicated(keep="first")]
            merged.columns = [c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c) for c in merged.columns]
            # Cache 6 hours
            self._cache.set(cache_key, merged.to_dict(), ttl_seconds=21600)
            return merged
        except Exception as exc:
            logger.warning(f"yfinance fetch_fundamentals_quarterly failed for {ticker}: {exc}")
            return pd.DataFrame()

    def fetch_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """Fetch OHLCV price history via yfinance."""
        cache_key = f"yf:price_history:{ticker}:{period}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                df = pd.DataFrame(cached)
                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"])
                return df
            except Exception:
                pass

        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=period)
            if hist is None or hist.empty:
                return pd.DataFrame()
            hist = hist.reset_index()
            hist.rename(columns={"index": "Date"}, inplace=True)
            if "Date" not in hist.columns and hist.index.name == "Date":
                hist = hist.reset_index()
            # Normalise date column
            if "Date" in hist.columns:
                hist["Date"] = pd.to_datetime(hist["Date"]).dt.tz_localize(None)
            # Cache 24h for price history
            payload = hist.copy()
            if "Date" in payload.columns:
                payload["Date"] = payload["Date"].astype(str)
            self._cache.set(cache_key, payload.to_dict(orient="list"), ttl_seconds=86400)
            return hist
        except Exception as exc:
            logger.warning(f"yfinance fetch_price_history failed for {ticker}: {exc}")
            return pd.DataFrame()

    def fetch_multi_price_history(
        self,
        tickers: list[str],
        period: str = "5y",
    ) -> dict[str, pd.DataFrame]:
        """Bulk OHLCV download for multiple tickers (one HTTP round-trip).

        Wraps ``yfinance.download(tickers, period=period, group_by="ticker",
        auto_adjust=True, progress=False)`` and splits the resulting
        MultiIndex DataFrame into one frame per ticker.

        Cached as parquet (not JSON) because the JSON cache cannot
        round-trip a DatetimeIndex reliably for large OHLCV payloads.
        24h TTL via mtime check.
        """
        import time as _time

        import yfinance as yf

        if not tickers:
            return {}

        # Hash-based cache key — collision-safe (no ambiguity between
        # ["AAPL_BAD"] vs ["AAPL","BAD"]) and path-traversal-safe (the
        # hex digest contains only [0-9a-f]).
        import hashlib

        cache_dir = self._cache._cache_dir / "multi_history"
        cache_dir.mkdir(parents=True, exist_ok=True)
        digest_input = "|".join(sorted(tickers)) + f"|{period}"
        digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
        parquet_path = cache_dir / f"{digest}.parquet"
        # Defence-in-depth path-traversal guard
        if not str(parquet_path.resolve()).startswith(str(cache_dir.resolve())):
            raise ValueError("Cache path escaped expected directory")

        if parquet_path.exists():
            age = _time.time() - parquet_path.stat().st_mtime
            if age < 86400:
                try:
                    df_cached = pd.read_parquet(parquet_path)
                    if isinstance(df_cached.columns, pd.MultiIndex):
                        return {
                            tk: df_cached[tk].dropna(how="all")
                            for tk in tickers
                            if tk in df_cached.columns.get_level_values(0)
                        }
                    return {tickers[0]: df_cached}
                except Exception as exc:
                    logger.debug(f"multi_history parquet read failed: {exc}")

        try:
            raw = yf.download(
                tickers=" ".join(tickers),
                period=period,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            logger.warning(f"yfinance.download failed for {tickers}: {exc}")
            return {}

        out: dict[str, pd.DataFrame] = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for tk in tickers:
                if tk in raw.columns.get_level_values(0):
                    sub = raw[tk].dropna(how="all")
                    if not sub.empty:
                        out[tk] = sub
        else:
            if not raw.empty:
                out[tickers[0]] = raw

        try:
            raw.to_parquet(parquet_path)
        except Exception as exc:
            logger.debug(f"multi_history parquet write failed: {exc}")
        return out

    def fetch_eps_estimates(self, ticker: str) -> pd.DataFrame | None:
        """Fetch analyst EPS estimates from yfinance earnings_estimate."""
        try:
            tk = yf.Ticker(ticker)
            # yfinance 0.2.x exposes analyst_price_targets or earnings_estimate
            est = getattr(tk, "earnings_estimate", None)
            if est is not None and not est.empty:
                return est
            return None
        except Exception as exc:
            logger.debug(f"yfinance fetch_eps_estimates failed for {ticker}: {exc}")
            return None

    # ------------------------------------------------------------------
    # yfinance.analysis surface (sub-project 2: analyst enrichment)
    # ------------------------------------------------------------------

    def fetch_recommendations_summary(self, ticker: str) -> dict[str, int]:
        """Return latest analyst rating counts (strong_buy/buy/hold/sell/strong_sell)."""
        cache_key = f"yf:rec_summary:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out = {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
        try:
            df = yf.Ticker(ticker).recommendations_summary
            if df is None or df.empty:
                return out
            row = df.iloc[0]
            mapping = {
                "strongBuy": "strong_buy",
                "buy": "buy",
                "hold": "hold",
                "sell": "sell",
                "strongSell": "strong_sell",
            }
            for src, dst in mapping.items():
                if src in row.index and pd.notna(row[src]):
                    out[dst] = int(row[src])
        except Exception as exc:
            logger.debug(f"yfinance fetch_recommendations_summary failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_eps_revisions(self, ticker: str) -> dict[str, int]:
        """Return revision counts up/down for 7d / 30d / 60d / 90d windows.

        Casing trap: yfinance uses ``upLast7days`` (lowercase) but ``downLast7Days``
        (capital D) for the 7-day column. Copy column names verbatim.
        """
        cache_key = f"yf:eps_revisions:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out = {
            "up_last_7d": 0,
            "down_last_7d": 0,
            "up_last_30d": 0,
            "down_last_30d": 0,
            "up_last_60d": 0,
            "down_last_60d": 0,
            "up_last_90d": 0,
            "down_last_90d": 0,
        }
        try:
            df = yf.Ticker(ticker).eps_revisions
            if df is None or df.empty:
                return out
            row = df.iloc[0]
            mapping = {
                "upLast7days": "up_last_7d",
                "downLast7Days": "down_last_7d",  # casing trap
                "upLast30days": "up_last_30d",
                "downLast30days": "down_last_30d",
                "upLast60days": "up_last_60d",
                "downLast60days": "down_last_60d",
                "upLast90days": "up_last_90d",
                "downLast90days": "down_last_90d",
            }
            for src, dst in mapping.items():
                if src in row.index and pd.notna(row[src]):
                    out[dst] = int(row[src])
        except Exception as exc:
            logger.debug(f"yfinance fetch_eps_revisions failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_eps_trend(self, ticker: str) -> list[dict[str, Any]]:
        """Return the rolling EPS-estimate trend (current / 7d ago / 30d / 60d / 90d)."""
        cache_key = f"yf:eps_trend:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: list[dict[str, Any]] = []
        try:
            df = yf.Ticker(ticker).eps_trend
            if df is None or df.empty:
                return out
            for label, row in df.iterrows():
                out.append(
                    {
                        "period": str(label),
                        "current": _safe_float(row.get("current")),
                        "n_minus_7d": _safe_float(row.get("7daysAgo")),
                        "n_minus_30d": _safe_float(row.get("30daysAgo")),
                        "n_minus_60d": _safe_float(row.get("60daysAgo")),
                        "n_minus_90d": _safe_float(row.get("90daysAgo")),
                    }
                )
        except Exception as exc:
            logger.debug(f"yfinance fetch_eps_trend failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_earnings_history(self, ticker: str, limit: int = 4) -> list[dict[str, Any]]:
        """Return last `limit` quarters of actual vs estimate vs surprise %.

        Empty for most non-US tickers — caller must degrade gracefully.
        ``limit`` is clamped to ``[1, 8]`` to prevent unbounded cache growth.
        """
        limit = max(1, min(int(limit), 8))
        cache_key = f"yf:earnings_history:{ticker}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: list[dict[str, Any]] = []
        try:
            df = yf.Ticker(ticker).earnings_history
            if df is None or df.empty:
                return out
            # Most-recent first (yfinance returns descending by quarter date)
            for idx, row in df.head(limit).iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                out.append(
                    {
                        "date": date_str,
                        "eps_actual": _safe_float(row.get("epsActual")),
                        "eps_estimate": _safe_float(row.get("epsEstimate")),
                        "eps_difference": _safe_float(row.get("epsDifference")),
                        "surprise_pct": _safe_float(row.get("surprisePercent")),
                    }
                )
        except Exception as exc:
            logger.debug(f"yfinance fetch_earnings_history failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_growth_estimates(self, ticker: str) -> dict[str, float | None]:
        """Return FY (+1y) / long-term growth estimates."""
        cache_key = f"yf:growth_estimates:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: dict[str, float | None] = {"fy_growth": None, "five_year_growth": None}
        try:
            df = yf.Ticker(ticker).growth_estimates
            if df is None or df.empty:
                return out
            for idx, row in df.iterrows():
                key = str(idx).lower()
                val = _safe_float(row.get("stockTrend"))
                if key in ("+1y", "1y", "next_year") and out["fy_growth"] is None:
                    out["fy_growth"] = val
                elif key in ("ltg", "+5y", "5y", "five_year") and out["five_year_growth"] is None:
                    out["five_year_growth"] = val
        except Exception as exc:
            logger.debug(f"yfinance fetch_growth_estimates failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_upgrades_downgrades(
        self,
        ticker: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the most recent `limit` analyst upgrades/downgrades.

        ``limit`` is clamped to ``[1, 50]`` (Phase 0 security review cap) to
        prevent unbounded cache growth + memory blow-up. Caller can slice further.
        """
        limit = max(1, min(int(limit), 50))
        cache_key = f"yf:upgrades_downgrades:{ticker}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: list[dict[str, Any]] = []
        try:
            df = yf.Ticker(ticker).upgrades_downgrades
            if df is None or df.empty:
                return out
            # Sort by date descending if the index is a DatetimeIndex
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.sort_index(ascending=False)
            for idx, row in df.head(limit).iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                out.append(
                    {
                        "date": date_str,
                        "firm": str(row.get("Firm", "")),
                        "to_grade": str(row.get("ToGrade", "")),
                        "from_grade": str(row.get("FromGrade", "")),
                        "action": str(row.get("Action", "")),
                    }
                )
        except Exception as exc:
            logger.debug(f"yfinance fetch_upgrades_downgrades failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_analyst_targets(self, ticker: str) -> dict[str, Any] | None:
        """Fetch consensus analyst price targets from yfinance info."""
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            target_mean = _safe_get(info, "targetMeanPrice", None)
            target_low = _safe_get(info, "targetLowPrice", None)
            target_high = _safe_get(info, "targetHighPrice", None)
            target_median = _safe_get(info, "targetMedianPrice", None)

            if all(
                v is None or (isinstance(v, float) and np.isnan(v))
                for v in [target_mean, target_low, target_high, target_median]
            ):
                return None

            return {
                "target_low": target_low if _is_finite_number(target_low) else None,
                "target_mean": target_mean if _is_finite_number(target_mean) else None,
                "target_high": target_high if _is_finite_number(target_high) else None,
                "target_median": target_median if _is_finite_number(target_median) else None,
                "num_analysts": _safe_get(info, "numberOfAnalystOpinions", None),
            }
        except Exception as exc:
            logger.warning(f"yfinance fetch_analyst_targets failed for {ticker}: {exc}")
            return None

    def fetch_news(self, ticker: str, limit: int = 20) -> list[dict[str, Any]] | None:
        """Fetch recent news headlines from yfinance."""
        try:
            tk = yf.Ticker(ticker)
            news = tk.news
            if not news:
                return None
            result = []
            for item in news[:limit]:
                # yfinance 0.2.40+ wraps news items under a "content" sub-dict;
                # older versions are flat. Support both.
                content = item.get("content", item)
                title = content.get("title", "") or item.get("title", "")
                published = content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime", "")
                publisher = (
                    content.get("provider", {}).get("displayName", "")
                    if isinstance(content.get("provider"), dict)
                    else item.get("publisher", "")
                )
                url = (
                    content.get("canonicalUrl", {}).get("url", "")
                    if isinstance(content.get("canonicalUrl"), dict)
                    else item.get("link", "")
                )
                result.append(
                    {
                        "title": title,
                        # M9 sentiment scorer reads `text` first; fall back to title.
                        "text": content.get("summary", "") or title,
                        # Keep both keys: `publishedAt` (M2) and `published_date` (M9 spec).
                        "publishedAt": published,
                        "published_date": published,
                        "source": publisher,
                        "url": url,
                    }
                )
            return result if result else None
        except Exception as exc:
            logger.debug(f"yfinance fetch_news failed for {ticker}: {exc}")
            return None

    def fetch_profile(self, ticker: str) -> dict[str, Any]:
        """Fetch company profile from yfinance info."""
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            country_raw = _safe_get(info, "country", "")
            country_code = _country_to_code(country_raw)

            first_trade_epoch = info.get("firstTradeDateEpochUtc")
            first_trade_date = None
            if first_trade_epoch is not None and _is_finite_number(first_trade_epoch):
                try:
                    dt = datetime.fromtimestamp(float(first_trade_epoch), tz=UTC)
                    first_trade_date = dt.date().isoformat()
                except (OverflowError, OSError, ValueError):
                    pass

            return {
                "Name": _safe_get(info, "shortName", _safe_get(info, "longName", ticker)),
                "Sector": _safe_get(info, "sector", ""),
                "Industry": _safe_get(info, "industry", ""),
                "Country": country_code,
                "Exchange": _safe_get(info, "exchange", ""),
                "FirstTradeDate": first_trade_date,
            }
        except Exception as exc:
            logger.warning(f"yfinance fetch_profile failed for {ticker}: {exc}")
            return {
                "Name": ticker,
                "Sector": "",
                "Industry": "",
                "Country": "",
                "Exchange": "",
                "FirstTradeDate": None,
            }

    # ------------------------------------------------------------------
    # yfinance.calendars surface (sub-project 3) — forward events + dividends
    # ------------------------------------------------------------------

    def fetch_calendar(self, ticker: str) -> dict[str, Any]:
        """Forward-looking earnings + dividend events from ``tk.calendar``.

        Source: ``tk.calendar`` (yfinance dict).  Returns the same fixed
        shape regardless of whether yfinance populated every key — missing
        fields become ``None``.  Cached for 6h.  Display-only payload.
        """
        cache_key = f"yf:calendar:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: dict[str, Any] = {
            "next_earnings_date": None,
            "next_earnings_eps_estimate": None,
            "next_earnings_eps_low": None,
            "next_earnings_eps_high": None,
            "next_earnings_revenue_estimate": None,
            "dividend_date": None,
            "ex_dividend_date": None,
        }
        try:
            cal = yf.Ticker(ticker).calendar
            if not cal:
                self._cache.set(cache_key, out, ttl_seconds=21600)
                return out

            earnings_dates = cal.get("Earnings Date")
            if isinstance(earnings_dates, list) and earnings_dates:
                first = earnings_dates[0]
                if hasattr(first, "isoformat"):
                    out["next_earnings_date"] = first.isoformat()

            out["next_earnings_eps_estimate"] = _safe_float(cal.get("Earnings Average"))
            out["next_earnings_eps_low"] = _safe_float(cal.get("Earnings Low"))
            out["next_earnings_eps_high"] = _safe_float(cal.get("Earnings High"))
            out["next_earnings_revenue_estimate"] = _safe_float(cal.get("Revenue Average"))

            div_date = cal.get("Dividend Date")
            if hasattr(div_date, "isoformat"):
                out["dividend_date"] = div_date.isoformat()
            ex_div = cal.get("Ex-Dividend Date")
            if hasattr(ex_div, "isoformat"):
                out["ex_dividend_date"] = ex_div.isoformat()
        except Exception as exc:
            logger.debug(f"yfinance fetch_calendar failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_dividends(
        self,
        ticker: str,
        years: int = 5,
    ) -> list[dict[str, Any]]:
        """Last ``years`` years of dividend payments from ``tk.dividends``.

        ``years`` is clamped to ``[1, 20]`` to bound cache size.  Index is
        tz-aware (US/Eastern) on yfinance Series; we strip tz before slicing
        so the API payload exposes pure ``YYYY-MM-DD`` dates and downstream
        consumers don't see Eastern-time offsets.  Cached for 6h.
        """
        years = max(1, min(int(years), 20))
        cache_key = f"yf:dividends:{ticker}:{years}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: list[dict[str, Any]] = []
        try:
            series = yf.Ticker(ticker).dividends
            if series is None or len(series) == 0:
                self._cache.set(cache_key, out, ttl_seconds=21600)
                return out

            idx = series.index
            if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
                series = series.copy()
                series.index = idx.tz_localize(None)

            cutoff = pd.Timestamp.now("UTC").tz_localize(None) - pd.DateOffset(years=years)
            filtered = series[series.index >= cutoff].sort_index()
            for ts, amount in filtered.items():
                amt = _safe_float(amount)
                if amt is None:
                    continue
                ex_date = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
                out.append({"ex_date": ex_date, "amount": amt})
        except Exception as exc:
            logger.debug(f"yfinance fetch_dividends failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    def fetch_info_yields(self, ticker: str) -> dict[str, float | None]:
        """Dividend yield + rate scalars from ``tk.info``.

        Returns the 4 dividend-related scalars yfinance exposes on the
        ``info`` dict.  Each is coerced via ``_safe_float`` and falls back
        to ``None`` on missing / non-finite values.  Cached for 6h.
        """
        cache_key = f"yf:info_yields:{ticker}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        out: dict[str, float | None] = {
            "dividend_yield": None,
            "dividend_rate": None,
            "trailing_annual_dividend_rate": None,
            "trailing_annual_dividend_yield": None,
        }
        try:
            info = yf.Ticker(ticker).info or {}
            out["dividend_yield"] = _safe_float(info.get("dividendYield"))
            out["dividend_rate"] = _safe_float(info.get("dividendRate"))
            out["trailing_annual_dividend_rate"] = _safe_float(info.get("trailingAnnualDividendRate"))
            out["trailing_annual_dividend_yield"] = _safe_float(info.get("trailingAnnualDividendYield"))
        except Exception as exc:
            logger.debug(f"yfinance fetch_info_yields failed for {ticker}: {exc}")
        self._cache.set(cache_key, out, ttl_seconds=21600)
        return out

    # ------------------------------------------------------------------
    # Composite fetch (used by HybridDataFetcher for the full scoring row)
    # ------------------------------------------------------------------

    def fetch_full_row(self, ticker: str) -> dict[str, Any]:
        """Fetch a complete scoring row for *ticker* using yfinance.

        This is the method that powers the legacy DataFetcher.fetch_single()
        path.  It pre-fetches all statements once and maps them to
        SCORING_COLUMNS.  Returns a flat dict with all fields (NaN when
        absent).
        """
        result: dict[str, Any] = {}

        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}

            if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
                logger.warning(f"No data returned from yfinance for {ticker}")
                return {}

            # Pre-fetch heavy DataFrames once
            try:
                financials = tk.financials
            except Exception as exc:
                logger.debug(f"{ticker}: financials fetch failed: {exc}")
                financials = None
            try:
                cashflow = tk.cashflow
            except Exception as exc:
                logger.debug(f"{ticker}: cashflow fetch failed: {exc}")
                cashflow = None
            try:
                balance_sheet = tk.balance_sheet
            except Exception as exc:
                logger.debug(f"{ticker}: balance_sheet fetch failed: {exc}")
                balance_sheet = None

            # Identification
            country_raw = _safe_get(info, "country", "")
            country_code = _country_to_code(country_raw)
            result["Name"] = _safe_get(info, "shortName", _safe_get(info, "longName", ticker))
            result["Sector"] = _safe_get(info, "sector", "")
            result["Industry"] = _safe_get(info, "industry", "")
            result["Country"] = country_code
            result["Exchange"] = _safe_get(info, "exchange", "")

            # Price & Size
            price = _safe_get(info, "currentPrice", _safe_get(info, "regularMarketPrice", np.nan))
            result["Price"] = price
            result["MarketCap"] = _safe_get(info, "marketCap", np.nan)
            result["EV"] = _safe_get(info, "enterpriseValue", np.nan)
            result["Shares"] = _safe_get(info, "sharesOutstanding", np.nan)

            # Income Statement
            ebitda = _safe_get(info, "ebitda", np.nan)
            result["Revenue"] = _safe_get(info, "totalRevenue", np.nan)
            result["EBITDA"] = ebitda
            result["EBIT"] = _get_real_ebit(tk, info, ebitda, cashflow=cashflow, financials=financials)
            result["NetIncome"] = _safe_get(info, "netIncomeToCommon", np.nan)

            # Cash Flow
            result["OperatingCashflow"] = _safe_get(info, "operatingCashflow", np.nan)
            result["FCF"] = _safe_get(info, "freeCashflow", np.nan)
            capex_val = _safe_get(info, "operatingCashflow", 0) - _safe_get(info, "freeCashflow", 0)
            result["CapEx"] = capex_val if capex_val != 0 else np.nan

            # Balance Sheet
            bs_items = _get_balance_sheet_items(tk, balance_sheet=balance_sheet)
            ta_info = _safe_get(info, "totalAssets", np.nan)
            result["TotalAssets"] = ta_info if _is_finite_number(ta_info) else bs_items["TotalAssets_BS"]
            equity_info = _safe_get(info, "totalStockholderEquity", np.nan)
            if _is_finite_number(equity_info):
                result["TotalEquity"] = equity_info
            elif _is_finite_number(bs_items["TotalEquity_BS"]):
                result["TotalEquity"] = bs_items["TotalEquity_BS"]
            else:
                bv = _safe_get(info, "bookValue", None)
                if bv is not None and _is_finite_number(bv):
                    sh = _safe_get(info, "sharesOutstanding", 1)
                    result["TotalEquity"] = float(bv) * float(sh)
                else:
                    result["TotalEquity"] = np.nan

            result["TotalDebt"] = _safe_get(info, "totalDebt", np.nan)
            result["Cash"] = _safe_get(info, "totalCash", np.nan)
            result["CurrentAssets"] = bs_items["CurrentAssets"]
            result["CurrentLiabilities"] = bs_items["CurrentLiabilities"]
            result["RetainedEarnings"] = bs_items["RetainedEarnings"]

            # Valuation Ratios
            result["PE"] = _safe_get(info, "trailingPE", np.nan)
            bvps = _safe_get(info, "bookValue", np.nan)
            if _is_finite_number(bvps) and bvps > 0 and _is_finite_number(price):
                result["PB"] = price / bvps
            else:
                result["PB"] = _safe_get(info, "priceToBook", np.nan)
            result["PS"] = _safe_get(info, "priceToSalesTrailing12Months", np.nan)

            fcf = _safe_get(info, "freeCashflow", np.nan)
            shares = _safe_get(info, "sharesOutstanding", np.nan)
            if _is_finite_number(fcf) and fcf > 0 and _is_finite_number(shares) and shares > 0:
                fcf_per_share = fcf / shares
                result["PFCF"] = price / fcf_per_share if _is_finite_number(price) and fcf_per_share > 0 else np.nan
            else:
                result["PFCF"] = np.nan

            ev = _safe_get(info, "enterpriseValue", np.nan)
            result["EV_EBITDA"] = _safe_div(ev, ebitda)
            rev = _safe_get(info, "totalRevenue", np.nan)
            result["EV_Sales"] = _safe_div(ev, rev)

            # Margins
            result["GrossMargin"] = _safe_get(info, "grossMargins", np.nan)
            result["OperatingMargin"] = _safe_get(info, "operatingMargins", np.nan)
            result["NetMargin"] = _safe_get(info, "profitMargins", np.nan)
            if _is_finite_number(fcf) and _is_finite_number(rev) and rev > 0:
                result["FCFMargin"] = fcf / rev
            else:
                result["FCFMargin"] = np.nan

            # Returns
            result["ROE"] = _safe_get(info, "returnOnEquity", np.nan)
            result["ROA"] = _safe_get(info, "returnOnAssets", np.nan)
            ebit_real = result["EBIT"]
            equity = result["TotalEquity"]
            debt = result["TotalDebt"]
            cash = result["Cash"]
            if all(_is_finite_number(x) for x in [ebit_real, equity, debt, cash]):
                invested_capital = float(equity) + float(debt) - float(cash)
                if invested_capital > 0:
                    result["ROIC"] = (float(ebit_real) * 0.75) / invested_capital
                else:
                    result["ROIC"] = np.nan
            else:
                result["ROIC"] = np.nan

            # Growth
            result["RevenueGrowth"] = _safe_get(info, "revenueGrowth", np.nan)

            # Balance Sheet Ratios
            result["CurrentRatio"] = _safe_get(info, "currentRatio", np.nan)
            result["DebtEquity"] = _safe_get(info, "debtToEquity", np.nan)
            if _is_finite_number(result["DebtEquity"]) and result["DebtEquity"] > 10:
                result["DebtEquity"] = result["DebtEquity"] / 100.0

            interest_expense = _get_real_interest_expense(tk, financials=financials)
            if _is_finite_number(ebit_real) and _is_finite_number(interest_expense) and interest_expense > 0:
                result["InterestCoverage"] = float(ebit_real) / float(interest_expense)
            else:
                result["InterestCoverage"] = np.nan

            # Shareholder
            result["DivYield"] = _safe_get(info, "dividendYield", np.nan)
            result["PayoutRatio"] = _safe_get(info, "payoutRatio", np.nan)

            # Risk
            result["Beta"] = _safe_get(info, "beta", np.nan)

            # Screener wiring
            result["AvgVolume"] = _safe_get(info, "averageDailyVolume3Month", np.nan)
            result["YearsListed"] = _years_since_first_trade(info)

            # Piotroski dilution
            result["Shares_PriorYear"] = _get_shares_prior_year(tk)

            # M4: Year-over-Year inputs for Piotroski deltas (real, not proxied)
            yoy = _get_yoy_inputs(
                balance_sheet=balance_sheet,
                financials=financials,
                cashflow=cashflow,
            )
            for k, v in yoy.items():
                result[k] = v

            # Extra fields
            result["ForwardPE"] = _safe_get(info, "forwardPE", np.nan)
            result["PEG"] = _safe_get(info, "pegRatio", np.nan)
            result["InsiderPct"] = _safe_get(info, "heldPercentInsiders", np.nan)
            result["InstitutionalPct"] = _safe_get(info, "heldPercentInstitutions", np.nan)
            result["ShortPctFloat"] = _safe_get(info, "shortPercentOfFloat", np.nan)
            result["FiftyTwoWeekHigh"] = _safe_get(info, "fiftyTwoWeekHigh", np.nan)
            result["FiftyTwoWeekLow"] = _safe_get(info, "fiftyTwoWeekLow", np.nan)

            # ------------------------------------------------------------------
            # M5 additions: history arrays + Beneish prior-year inputs
            # ------------------------------------------------------------------
            history_fields = self._extract_history_and_prior(
                financials=financials,
                balance_sheet=balance_sheet,
                cashflow=cashflow,
                current_ebit=result.get("EBIT"),
                current_equity=result.get("TotalEquity"),
                current_debt=result.get("TotalDebt"),
                current_cash=result.get("Cash"),
            )
            result.update(history_fields)
            # WACC placeholder (M6 fills the real value)
            result["WACC"] = np.nan

        except Exception as exc:
            logger.error(f"yfinance fetch_full_row failed for {ticker}: {exc}")

        return result

    # ------------------------------------------------------------------
    # M5: history + Beneish prior-year extraction (yfinance variant)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_history_and_prior(
        financials: pd.DataFrame | None,
        balance_sheet: pd.DataFrame | None,
        cashflow: pd.DataFrame | None,
        current_ebit: float | None = None,
        current_equity: float | None = None,
        current_debt: float | None = None,
        current_cash: float | None = None,
    ) -> dict[str, Any]:
        """Pull 5y / 3y history arrays + Beneish prior-year scalars from yfinance.

        Tolerant of gaps: every field defaults to NaN or [] when yfinance does
        not return the underlying line item.
        """
        out: dict[str, Any] = {}

        def _series_at(stmt: pd.DataFrame | None, keys: Sequence[str]) -> list[float]:
            """Return finite numeric values from row matching any key, ordered most-recent first."""
            if stmt is None or not isinstance(stmt, pd.DataFrame) or stmt.empty:
                return []
            for k in keys:
                if k in stmt.index:
                    row = stmt.loc[k]
                    if isinstance(row, pd.DataFrame):
                        if row.empty:
                            continue
                        row = row.iloc[0]
                    vals: list[float] = []
                    for c in row.index:
                        v = row[c]
                        if _is_finite_number(v):
                            vals.append(float(v))
                    if vals:
                        return vals
            return []

        # Income-statement series
        revenue_hist = _series_at(financials, ["Total Revenue", "TotalRevenue", "Revenue"])
        ni_hist = _series_at(financials, ["Net Income", "NetIncome", "Net Income Common Stockholders"])
        ebit_hist = _series_at(financials, ["EBIT", "Operating Income", "OperatingIncome"])
        op_inc_hist = ebit_hist
        cogs_hist = _series_at(financials, ["Cost Of Revenue", "Cost Of Goods Sold", "CostOfRevenue"])
        sga_hist = _series_at(
            financials, ["Selling General And Administration", "SellingGeneralAndAdministrative", "SG&A Expense"]
        )
        gross_profit_hist = _series_at(financials, ["Gross Profit", "GrossProfit"])
        interest_hist = _series_at(financials, ["Interest Expense", "InterestExpense"])

        # Balance-sheet series
        ta_hist = _series_at(balance_sheet, ["Total Assets", "TotalAssets"])
        ca_hist = _series_at(balance_sheet, ["Current Assets", "Total Current Assets", "CurrentAssets"])
        cl_hist = _series_at(balance_sheet, ["Current Liabilities", "Total Current Liabilities", "CurrentLiabilities"])
        recv_hist = _series_at(
            balance_sheet, ["Net Receivables", "Receivables", "AccountsReceivable", "Accounts Receivable"]
        )
        ppe_hist = _series_at(
            balance_sheet, ["Net PPE", "Property Plant Equipment Net", "Net Property Plant And Equipment"]
        )
        ltd_hist = _series_at(balance_sheet, ["Long Term Debt", "LongTermDebt"])
        equity_hist = _series_at(
            balance_sheet, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]
        )
        debt_hist = _series_at(balance_sheet, ["Total Debt", "TotalDebt"])
        cash_hist = _series_at(balance_sheet, ["Cash And Cash Equivalents", "CashAndCashEquivalents", "Cash"])

        # Cash-flow series
        fcf_hist = _series_at(cashflow, ["Free Cash Flow", "FreeCashFlow"])
        op_cf_hist = _series_at(
            cashflow, ["Operating Cash Flow", "OperatingCashFlow", "Cash Flow From Continuing Operating Activities"]
        )
        capex_hist = _series_at(cashflow, ["Capital Expenditure", "CapitalExpenditure", "Capital Expenditures"])
        da_hist = _series_at(
            cashflow,
            ["Depreciation And Amortization", "DepreciationAndAmortization", "Depreciation Amortization Depletion"],
        )

        # FCF fallback: OCF - |CapEx|
        if not fcf_hist and op_cf_hist and capex_hist:
            n = min(len(op_cf_hist), len(capex_hist))
            fcf_hist = [op_cf_hist[i] - abs(capex_hist[i]) for i in range(n)]

        # Operating-margin history (op_income / revenue)
        op_margin_hist: list[float] = []
        if op_inc_hist and revenue_hist:
            n = min(len(op_inc_hist), len(revenue_hist))
            for i in range(n):
                if revenue_hist[i] != 0:
                    op_margin_hist.append(op_inc_hist[i] / revenue_hist[i])

        # ROIC + invested-capital history
        roic_hist: list[float] = []
        ic_hist: list[float] = []
        if ebit_hist and equity_hist and debt_hist and cash_hist:
            n = min(len(ebit_hist), len(equity_hist), len(debt_hist), len(cash_hist))
            for i in range(n):
                invested = equity_hist[i] + debt_hist[i] - cash_hist[i]
                if invested > 0:
                    roic_hist.append((ebit_hist[i] * 0.75) / invested)
                    ic_hist.append(invested)

        # Most-recent-first conventions
        out["FCF_History_5y"] = fcf_hist[:5]
        out["NetIncome_History_5y"] = ni_hist[:5]
        out["ROIC_History_5y"] = roic_hist[:5]
        out["OperatingMargin_History_5y"] = op_margin_hist[:5]
        out["EBIT_History_3y"] = ebit_hist[:3]
        out["InvestedCapital_History_3y"] = ic_hist[:3]

        # Beneish prior-year scalars
        def _idx(seq: list[float], i: int) -> float:
            return seq[i] if 0 <= i < len(seq) else float("nan")

        out.setdefault("Receivables", _idx(recv_hist, 0))
        out["Receivables_PriorYear"] = _idx(recv_hist, 1)
        out["Revenue_PriorYear"] = _idx(revenue_hist, 1)
        if gross_profit_hist and revenue_hist:
            n = min(len(gross_profit_hist), len(revenue_hist))
            gm_hist = [gross_profit_hist[i] / revenue_hist[i] for i in range(n) if revenue_hist[i] != 0]
            out["GrossMargin_PriorYear"] = _idx(gm_hist, 1)
        else:
            out["GrossMargin_PriorYear"] = float("nan")
        out["TotalAssets_PriorYear"] = _idx(ta_hist, 1)
        out["CurrentAssets_PriorYear"] = _idx(ca_hist, 1)
        out["CurrentLiabilities_PriorYear"] = _idx(cl_hist, 1)
        out["PPE"] = _idx(ppe_hist, 0)
        out["PPE_PriorYear"] = _idx(ppe_hist, 1)
        out["DepreciationAmortization"] = _idx(da_hist, 0)
        out["DepreciationAmortization_PriorYear"] = _idx(da_hist, 1)
        out["SGA"] = _idx(sga_hist, 0)
        out["SGA_PriorYear"] = _idx(sga_hist, 1)
        out["LongTermDebt"] = _idx(ltd_hist, 0)
        out["LongTermDebt_PriorYear"] = _idx(ltd_hist, 1)
        out["COGS"] = _idx(cogs_hist, 0)
        # Real interest expense scalar (positive convention)
        out["InterestExpense"] = abs(_idx(interest_hist, 0)) if np.isfinite(_idx(interest_hist, 0)) else float("nan")

        return out
