"""
Invest Solo -- YFinanceDataFetcher
Wraps all yfinance calls and exposes the MarketDataSource Protocol surface.

The heavy helper functions (_latest_from_statement, _get_real_ebit, etc.) are
lifted directly from M1's data_fetcher.py to avoid duplication.  data_fetcher.py
is kept as a compatibility shim over HybridDataFetcher and no longer contains
the yfinance plumbing directly; this module owns it.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from backend.app.services.cache_service import CacheService


# ---------------------------------------------------------------------------
# Low-level helpers (moved from data_fetcher.py)
# ---------------------------------------------------------------------------

def _safe_get(info: Dict[str, Any], key: str, default: Any = np.nan) -> Any:
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


def _latest_from_statement(
    statement: Optional[pd.DataFrame],
    candidate_keys: Sequence[str],
) -> float:
    """Pull the most-recent value of any candidate row label from a yfinance statement.

    yfinance statements (``tk.financials``, ``tk.balance_sheet``, ``tk.cashflow``)
    are DataFrames where rows are line items and columns are period-end dates with
    the most recent first. We probe ``candidate_keys`` in order and return the
    first non-NaN, non-zero value from the most-recent column. Returns NaN if
    nothing is found. Never raises.
    """
    if statement is None or not isinstance(statement, pd.DataFrame) or statement.empty:
        return np.nan
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
        for col in row.index:
            val = row[col]
            if _is_finite_number(val) and float(val) != 0:
                return float(val)
    return np.nan


def _get_real_ebit(
    tk: "yf.Ticker",
    info: Dict[str, Any],
    ebitda: float,
    cashflow: Optional[pd.DataFrame] = None,
    financials: Optional[pd.DataFrame] = None,
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
    tk: "yf.Ticker",
    financials: Optional[pd.DataFrame] = None,
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


def _get_shares_prior_year(tk: "yf.Ticker") -> float:
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
    tk: "yf.Ticker",
    balance_sheet: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
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


def _years_since_first_trade(info: Dict[str, Any]) -> float:
    """Compute years since first listing from ``firstTradeDateEpochUtc``."""
    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is None or not _is_finite_number(epoch):
        return np.nan
    try:
        first_trade = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
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

    def __init__(self, cache: Optional[CacheService] = None) -> None:
        self._cache = cache or CacheService()

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def fetch_quote(self, ticker: str) -> Dict[str, Any]:
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
            merged.columns = [
                c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c)
                for c in merged.columns
            ]
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
            merged.columns = [
                c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c)
                for c in merged.columns
            ]
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

    def fetch_eps_estimates(self, ticker: str) -> Optional[pd.DataFrame]:
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

    def fetch_eps_revisions(self, ticker: str) -> Optional[pd.DataFrame]:
        """yfinance does not provide EPS revision history.

        Raises ``NotImplementedError`` so the hybrid composer falls through to FMP.
        """
        raise NotImplementedError("yfinance does not provide EPS revision history")

    def fetch_analyst_targets(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch consensus analyst price targets from yfinance info."""
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            target_mean = _safe_get(info, "targetMeanPrice", None)
            target_low = _safe_get(info, "targetLowPrice", None)
            target_high = _safe_get(info, "targetHighPrice", None)
            target_median = _safe_get(info, "targetMedianPrice", None)

            if all(v is None or (isinstance(v, float) and np.isnan(v))
                   for v in [target_mean, target_low, target_high, target_median]):
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

    def fetch_news(self, ticker: str, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
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
                published = (
                    content.get("pubDate")
                    or content.get("displayTime")
                    or item.get("providerPublishTime", "")
                )
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
                result.append({
                    "title": title,
                    # M9 sentiment scorer reads `text` first; fall back to title.
                    "text": content.get("summary", "") or title,
                    # Keep both keys: `publishedAt` (M2) and `published_date` (M9 spec).
                    "publishedAt": published,
                    "published_date": published,
                    "source": publisher,
                    "url": url,
                })
            return result if result else None
        except Exception as exc:
            logger.debug(f"yfinance fetch_news failed for {ticker}: {exc}")
            return None

    def fetch_profile(self, ticker: str) -> Dict[str, Any]:
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
                    dt = datetime.fromtimestamp(float(first_trade_epoch), tz=timezone.utc)
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
    # Composite fetch (used by HybridDataFetcher for the full scoring row)
    # ------------------------------------------------------------------

    def fetch_full_row(self, ticker: str) -> Dict[str, Any]:
        """Fetch a complete scoring row for *ticker* using yfinance.

        This is the method that powers the legacy DataFetcher.fetch_single()
        path.  It pre-fetches all statements once and maps them to
        SCORING_COLUMNS.  Returns a flat dict with all fields (NaN when
        absent).
        """
        result: Dict[str, Any] = {}

        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}

            if not info or (
                info.get("regularMarketPrice") is None
                and info.get("currentPrice") is None
            ):
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
            capex_val = (
                _safe_get(info, "operatingCashflow", 0) - _safe_get(info, "freeCashflow", 0)
            )
            result["CapEx"] = capex_val if capex_val != 0 else np.nan

            # Balance Sheet
            bs_items = _get_balance_sheet_items(tk, balance_sheet=balance_sheet)
            ta_info = _safe_get(info, "totalAssets", np.nan)
            result["TotalAssets"] = (
                ta_info if _is_finite_number(ta_info) else bs_items["TotalAssets_BS"]
            )
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
                result["PFCF"] = (
                    price / fcf_per_share
                    if _is_finite_number(price) and fcf_per_share > 0
                    else np.nan
                )
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
            if (
                _is_finite_number(ebit_real)
                and _is_finite_number(interest_expense)
                and interest_expense > 0
            ):
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

            # Extra fields
            result["ForwardPE"] = _safe_get(info, "forwardPE", np.nan)
            result["PEG"] = _safe_get(info, "pegRatio", np.nan)
            result["InsiderPct"] = _safe_get(info, "heldPercentInsiders", np.nan)
            result["InstitutionalPct"] = _safe_get(info, "heldPercentInstitutions", np.nan)
            result["ShortPctFloat"] = _safe_get(info, "shortPercentOfFloat", np.nan)
            result["FiftyTwoWeekHigh"] = _safe_get(info, "fiftyTwoWeekHigh", np.nan)
            result["FiftyTwoWeekLow"] = _safe_get(info, "fiftyTwoWeekLow", np.nan)

        except Exception as exc:
            logger.error(f"yfinance fetch_full_row failed for {ticker}: {exc}")

        return result
