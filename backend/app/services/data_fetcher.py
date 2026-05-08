"""
Invest Solo -- Data Fetcher Service
Fetches live data from yfinance and maps it to the exact column format
expected by scoring_engine.py.
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from backend.app.config import settings
from backend.app.services.cache_service import CacheService


# The scoring engine expects these exact column names.
# Frontend reads composite/sub scores; columns added in M1 (CurrentAssets,
# CurrentLiabilities, RetainedEarnings, AvgVolume, YearsListed,
# Shares_PriorYear) are new and consumed only by scoring_engine internals.
SCORING_COLUMNS = [
    "PE", "PB", "PS", "PFCF", "EV_EBITDA", "EV_Sales",
    "ROE", "ROA", "ROIC", "OperatingMargin", "NetMargin", "FCFMargin", "GrossMargin",
    "RevenueGrowth", "CurrentRatio", "DebtEquity", "InterestCoverage",
    "DivYield", "PayoutRatio", "Beta",
    "Price", "MarketCap", "EV", "Shares",
    "Revenue", "EBITDA", "EBIT", "NetIncome", "FCF", "OperatingCashflow", "CapEx",
    "TotalAssets", "TotalEquity", "TotalDebt", "Cash",
    # M1 additions (real Altman Z'' inputs, real Piotroski dilution check, screener wiring)
    "CurrentAssets", "CurrentLiabilities", "RetainedEarnings",
    "AvgVolume", "YearsListed", "Shares_PriorYear",
    "Name", "Sector", "Industry", "Country", "Exchange",
    "PEA", "PEA_PME",
]

# Extra fields we fetch beyond what the scoring engine needs
EXTRA_FIELDS = [
    "ForwardPE", "PEG", "InsiderPct", "InstitutionalPct",
    "ShortPctFloat", "FiftyTwoWeekHigh", "FiftyTwoWeekLow",
]


def _safe_get(info: Dict[str, Any], key: str, default: Any = np.nan) -> Any:
    """Safely extract a value from yfinance info dict."""
    val = info.get(key, default)
    if val is None:
        return default
    return val


def _safe_div(numerator: Any, denominator: Any) -> float:
    """Safe division returning NaN on division by zero or invalid inputs."""
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

    yfinance statements (`tk.financials`, `tk.balance_sheet`, `tk.cashflow`) are
    DataFrames where rows are line items and columns are period-end dates with
    the most recent first. Some labels exist as `EBIT`, others as `Operating Income`,
    `Interest Expense` vs `Interest Expense, Net Operating Interest Expense`, etc.
    We probe `candidate_keys` in order and return the first non-NaN, non-zero
    value from the most-recent column. Returns NaN if nothing is found.

    Never raises -- statement access errors surface as NaN.
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
        # If multiple rows share the label, .loc returns a DataFrame; take the first.
        if isinstance(row, pd.DataFrame):
            if row.empty:
                continue
            row = row.iloc[0]
        # Walk columns left-to-right (most recent first) and return first valid value.
        for col in row.index:
            val = row[col]
            if _is_finite_number(val) and float(val) != 0:
                return float(val)
        # All values were NaN/0 -- keep probing other candidate keys.
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
        1. `tk.financials.loc["EBIT"]` (most recent column)
        2. `tk.financials.loc["Operating Income"]` / `OperatingIncome`
        3. Fallback: `EBITDA - D&A` where D&A comes from cashflow
        4. NaN

    Returns
    -------
    float
        EBIT in the same currency/scale as the income statement, or NaN.
    """
    try:
        if financials is None:
            financials = tk.financials
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"financials access failed: {exc}")
        financials = None

    ebit = _latest_from_statement(
        financials,
        ["EBIT", "Operating Income", "OperatingIncome", "Total Operating Income As Reported"],
    )
    if _is_finite_number(ebit):
        return ebit

    # Fallback: EBIT = EBITDA - D&A (D&A from cashflow)
    if not _is_finite_number(ebitda):
        return np.nan
    try:
        if cashflow is None:
            cashflow = tk.cashflow
    except Exception as exc:  # noqa: BLE001
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

    yfinance often returns interest expense as a NEGATIVE number (expense
    convention); we return a POSITIVE value so downstream `EBIT / interest`
    behaves intuitively. Returns NaN if not available -- never fabricates.
    """
    try:
        if financials is None:
            financials = tk.financials
    except Exception as exc:  # noqa: BLE001
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
    """Get shares outstanding ~1 year ago via `tk.get_shares_full()`.

    Returns NaN if the API returns nothing or fails. The Piotroski no-dilution
    signal compares this to the latest sharesOutstanding.
    """
    try:
        s = tk.get_shares_full()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"get_shares_full failed: {exc}")
        return np.nan
    if s is None or len(s) == 0:
        return np.nan
    try:
        s = s.dropna()
        if s.empty:
            return np.nan
        # Pick a value from approx 365 days before the most recent point.
        idx = pd.to_datetime(s.index, utc=True, errors="coerce")
        # `idx` may be a pandas DatetimeIndex (has .isna()) or a plain ndarray
        # depending on the input. Normalise to DatetimeIndex.
        idx = pd.DatetimeIndex(idx)
        if idx.isna().all():
            return float(s.iloc[0])
        latest_ts = idx.max()
        target_ts = latest_ts - pd.Timedelta(days=365)
        # Find row at or before target_ts (use prev observation = most recent <= target)
        mask = idx <= target_ts
        # `mask` is a numpy bool array; index into the Series with it directly.
        mask_arr = np.asarray(mask)
        if mask_arr.any():
            sub = s.iloc[np.flatnonzero(mask_arr)]
            if not sub.empty:
                return float(sub.iloc[-1])
        # Fallback: use the earliest available (still NaN-better than nothing)
        return float(s.iloc[0])
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"shares prior year extraction failed: {exc}")
        return np.nan


def _get_balance_sheet_items(
    tk: "yf.Ticker",
    balance_sheet: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Fetch CurrentAssets, CurrentLiabilities, RetainedEarnings from balance sheet.

    All three are required for the real Altman Z / Z'' computation. Each is NaN
    if absent -- scoring engine handles NaNs by skipping that signal.
    """
    try:
        if balance_sheet is None:
            balance_sheet = tk.balance_sheet
    except Exception as exc:  # noqa: BLE001
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
        # M1: TotalAssets from balance sheet as backup -- yfinance `info`
        # frequently lacks `totalAssets` for European tickers and even some
        # US ones (e.g. AAPL), which kept Altman Z stuck at NaN.
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
    """Compute years since first listing from `firstTradeDateEpochUtc`."""
    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is None or not _is_finite_number(epoch):
        return np.nan
    try:
        first_trade = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        return (now - first_trade).days / 365.25
    except (OverflowError, OSError, ValueError):
        return np.nan


class DataFetcher:
    """Fetches financial data from yfinance and maps to the scoring schema."""

    def __init__(self, cache: Optional[CacheService] = None) -> None:
        self._cache = cache or CacheService()
        self._pea_countries = settings.pea_eligible_countries
        self._delay = settings.request_delay_seconds

    def _determine_pea_eligible(self, country: str) -> bool:
        """Check PEA eligibility from country code."""
        if not country:
            return False
        return country.upper() in self._pea_countries

    def fetch_single(self, ticker_symbol: str) -> Dict[str, Any]:
        """
        Fetch data for a single ticker from yfinance and map to scoring schema.

        Returns a dict with keys matching SCORING_COLUMNS plus EXTRA_FIELDS.
        Missing fields are filled with np.nan -- never fabricated proxies.
        """
        # Check cache first
        cache_key = f"ticker_{ticker_symbol}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {ticker_symbol}")
            return cached

        logger.info(f"Fetching live data for {ticker_symbol}")
        result: Dict[str, Any] = {col: np.nan for col in SCORING_COLUMNS + EXTRA_FIELDS}
        result["Ticker"] = ticker_symbol

        try:
            tk = yf.Ticker(ticker_symbol)
            info = tk.info or {}

            if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
                logger.warning(f"No data returned for {ticker_symbol}")
                result["Name"] = ticker_symbol
                result["Sector"] = ""
                result["Industry"] = ""
                result["Country"] = ""
                result["Exchange"] = ""
                result["PEA"] = False
                result["PEA_PME"] = False
                self._cache.set(cache_key, result, ttl_seconds=3600)
                return result

            # Pre-fetch the heavy DataFrames once -- yfinance caches per-ticker.
            try:
                financials = tk.financials
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"{ticker_symbol}: financials fetch failed: {exc}")
                financials = None
            try:
                cashflow = tk.cashflow
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"{ticker_symbol}: cashflow fetch failed: {exc}")
                cashflow = None
            try:
                balance_sheet = tk.balance_sheet
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"{ticker_symbol}: balance_sheet fetch failed: {exc}")
                balance_sheet = None

            # -- Identification --
            result["Name"] = _safe_get(info, "shortName", _safe_get(info, "longName", ticker_symbol))
            result["Sector"] = _safe_get(info, "sector", "")
            result["Industry"] = _safe_get(info, "industry", "")
            country_raw = _safe_get(info, "country", "")
            # Map country name to ISO code (simple mapping for major markets)
            country_code = self._country_to_code(country_raw)
            result["Country"] = country_code
            result["Exchange"] = _safe_get(info, "exchange", "")

            # -- PEA eligibility --
            result["PEA"] = self._determine_pea_eligible(country_code)
            # PEA-PME: market cap < 2B EUR (simplified heuristic)
            mktcap = _safe_get(info, "marketCap", 0)
            result["PEA_PME"] = result["PEA"] and (0 < mktcap < 2_000_000_000)

            # -- Price & Size --
            price = _safe_get(info, "currentPrice", _safe_get(info, "regularMarketPrice", np.nan))
            result["Price"] = price
            result["MarketCap"] = _safe_get(info, "marketCap", np.nan)
            result["EV"] = _safe_get(info, "enterpriseValue", np.nan)
            result["Shares"] = _safe_get(info, "sharesOutstanding", np.nan)

            # -- Income Statement --
            ebitda = _safe_get(info, "ebitda", np.nan)
            result["Revenue"] = _safe_get(info, "totalRevenue", np.nan)
            result["EBITDA"] = ebitda
            # BUG FIX #1 (M1): EBIT from real income statement, never aliased to EBITDA.
            result["EBIT"] = _get_real_ebit(tk, info, ebitda, cashflow=cashflow, financials=financials)
            result["NetIncome"] = _safe_get(info, "netIncomeToCommon", np.nan)

            # -- Cash Flow --
            result["OperatingCashflow"] = _safe_get(info, "operatingCashflow", np.nan)
            result["FCF"] = _safe_get(info, "freeCashflow", np.nan)
            capex_val = _safe_get(info, "operatingCashflow", 0) - _safe_get(info, "freeCashflow", 0)
            result["CapEx"] = capex_val if capex_val != 0 else np.nan

            # -- Balance Sheet --
            # M1: pull balance-sheet items directly (yfinance `info` frequently
            # lacks `totalAssets`, which left Altman Z stuck at NaN).
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
                # Last-ditch: bookValue × shares (legacy behaviour)
                bv = _safe_get(info, "bookValue", None)
                if bv is not None and _is_finite_number(bv):
                    sh = _safe_get(info, "sharesOutstanding", 1)
                    result["TotalEquity"] = float(bv) * float(sh)
                else:
                    result["TotalEquity"] = np.nan

            result["TotalDebt"] = _safe_get(info, "totalDebt", np.nan)
            result["Cash"] = _safe_get(info, "totalCash", np.nan)

            # M1: Real Altman Z'' inputs from balance sheet.
            result["CurrentAssets"] = bs_items["CurrentAssets"]
            result["CurrentLiabilities"] = bs_items["CurrentLiabilities"]
            result["RetainedEarnings"] = bs_items["RetainedEarnings"]

            # -- Valuation Ratios (prefer yfinance computed, fall back to manual) --
            pe = _safe_get(info, "trailingPE", np.nan)
            result["PE"] = pe

            bvps = _safe_get(info, "bookValue", np.nan)
            if not np.isnan(bvps) and bvps > 0 and not np.isnan(price):
                result["PB"] = price / bvps
            else:
                result["PB"] = _safe_get(info, "priceToBook", np.nan)

            result["PS"] = _safe_get(info, "priceToSalesTrailing12Months", np.nan)

            # P/FCF: computed
            fcf = _safe_get(info, "freeCashflow", np.nan)
            shares = _safe_get(info, "sharesOutstanding", np.nan)
            if not np.isnan(fcf) and fcf > 0 and not np.isnan(shares) and shares > 0:
                fcf_per_share = fcf / shares
                result["PFCF"] = price / fcf_per_share if not np.isnan(price) and fcf_per_share > 0 else np.nan
            else:
                result["PFCF"] = np.nan

            # EV/EBITDA
            ev = _safe_get(info, "enterpriseValue", np.nan)
            result["EV_EBITDA"] = _safe_div(ev, ebitda)

            # EV/Sales
            rev = _safe_get(info, "totalRevenue", np.nan)
            result["EV_Sales"] = _safe_div(ev, rev)

            # -- Margins --
            result["GrossMargin"] = _safe_get(info, "grossMargins", np.nan)
            result["OperatingMargin"] = _safe_get(info, "operatingMargins", np.nan)
            result["NetMargin"] = _safe_get(info, "profitMargins", np.nan)
            # FCF margin: computed
            if not np.isnan(fcf) and not np.isnan(rev) and rev > 0:
                result["FCFMargin"] = fcf / rev
            else:
                result["FCFMargin"] = np.nan

            # -- Returns --
            result["ROE"] = _safe_get(info, "returnOnEquity", np.nan)
            result["ROA"] = _safe_get(info, "returnOnAssets", np.nan)
            # ROIC: EBIT*(1-tax) / (Equity + Debt - Cash)
            # BUG FIX #2 (M1): use the real EBIT from #1, not the EBITDA proxy.
            ebit_real = result["EBIT"]
            equity = result["TotalEquity"]
            debt = result["TotalDebt"]
            cash = result["Cash"]
            if all(_is_finite_number(x) for x in [ebit_real, equity, debt, cash]):
                invested_capital = float(equity) + float(debt) - float(cash)
                if invested_capital > 0:
                    # Hardcoded 25% tax for now; M5 will make this country-aware.
                    result["ROIC"] = (float(ebit_real) * 0.75) / invested_capital
                else:
                    result["ROIC"] = np.nan
            else:
                result["ROIC"] = np.nan

            # -- Growth --
            result["RevenueGrowth"] = _safe_get(info, "revenueGrowth", np.nan)

            # -- Balance Sheet Ratios --
            result["CurrentRatio"] = _safe_get(info, "currentRatio", np.nan)
            result["DebtEquity"] = _safe_get(info, "debtToEquity", np.nan)
            # yfinance debtToEquity is in percentage (e.g. 45 means 0.45)
            if not np.isnan(result["DebtEquity"]) and result["DebtEquity"] > 10:
                result["DebtEquity"] = result["DebtEquity"] / 100.0

            # BUG FIX #3 (M1): Real Interest Expense from financials, never the
            # `totalDebt * 0.04` fabrication. NaN when not available.
            interest_expense = _get_real_interest_expense(tk, financials=financials)
            if (
                _is_finite_number(ebit_real)
                and _is_finite_number(interest_expense)
                and interest_expense > 0
            ):
                # Coverage = EBIT / Interest (textbook). EBITDA was the prior
                # numerator only because EBIT was unavailable; keep EBIT for
                # consistency now that we have it real.
                result["InterestCoverage"] = float(ebit_real) / float(interest_expense)
            else:
                result["InterestCoverage"] = np.nan

            # -- Shareholder --
            result["DivYield"] = _safe_get(info, "dividendYield", np.nan)
            result["PayoutRatio"] = _safe_get(info, "payoutRatio", np.nan)

            # -- Risk --
            result["Beta"] = _safe_get(info, "beta", np.nan)

            # -- Screener wiring fields (M1 bug #8) --
            result["AvgVolume"] = _safe_get(info, "averageDailyVolume3Month", np.nan)
            result["YearsListed"] = _years_since_first_trade(info)

            # -- Real shares-outstanding YoY for Piotroski no-dilution check (M1 bug #5) --
            result["Shares_PriorYear"] = _get_shares_prior_year(tk)

            # -- Extra fields (not used by scoring engine) --
            result["ForwardPE"] = _safe_get(info, "forwardPE", np.nan)
            result["PEG"] = _safe_get(info, "pegRatio", np.nan)
            result["InsiderPct"] = _safe_get(info, "heldPercentInsiders", np.nan)
            result["InstitutionalPct"] = _safe_get(info, "heldPercentInstitutions", np.nan)
            result["ShortPctFloat"] = _safe_get(info, "shortPercentOfFloat", np.nan)
            result["FiftyTwoWeekHigh"] = _safe_get(info, "fiftyTwoWeekHigh", np.nan)
            result["FiftyTwoWeekLow"] = _safe_get(info, "fiftyTwoWeekLow", np.nan)

            # Cache the result (4 hour TTL)
            self._cache.set(cache_key, result, ttl_seconds=14400)

        except Exception as exc:
            logger.error(f"Error fetching {ticker_symbol}: {exc}")
            result["Name"] = ticker_symbol
            result["Sector"] = ""
            result["Industry"] = ""
            result["Country"] = ""
            result["Exchange"] = ""
            result["PEA"] = False
            result["PEA_PME"] = False

        return result

    def fetch_batch(self, tickers: List[str]) -> pd.DataFrame:
        """
        Fetch data for multiple tickers and return a DataFrame
        indexed by Ticker with columns matching the scoring schema.
        """
        rows: List[Dict[str, Any]] = []
        for i, ticker in enumerate(tickers):
            data = self.fetch_single(ticker)
            data["Ticker"] = ticker
            rows.append(data)
            # Rate limiting (skip delay if data came from cache)
            if i < len(tickers) - 1:
                time.sleep(self._delay)

        if not rows:
            return pd.DataFrame(columns=["Ticker"] + SCORING_COLUMNS)

        df = pd.DataFrame(rows)
        df.set_index("Ticker", inplace=True)
        return df

    def fetch_analyst_ratings(self, ticker_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch analyst recommendation data from yfinance.
        Returns a dict compatible with AnalystRatings or None.
        """
        try:
            tk = yf.Ticker(ticker_symbol)
            info = tk.info or {}

            target_mean = _safe_get(info, "targetMeanPrice", None)
            target_low = _safe_get(info, "targetLowPrice", None)
            target_high = _safe_get(info, "targetHighPrice", None)
            target_median = _safe_get(info, "targetMedianPrice", None)
            recommendation = _safe_get(info, "recommendationKey", "")

            # Try to get recommendation counts from the recommendations endpoint
            buy = 0
            hold = 0
            sell = 0
            strong_buy = 0
            strong_sell = 0

            try:
                recs = tk.recommendations
                if recs is not None and not recs.empty:
                    # Take the most recent period
                    latest = recs.iloc[-1] if len(recs) > 0 else None
                    if latest is not None:
                        strong_buy = int(latest.get("strongBuy", 0))
                        buy = int(latest.get("buy", 0))
                        hold = int(latest.get("hold", 0))
                        sell = int(latest.get("sell", 0))
                        strong_sell = int(latest.get("strongSell", 0))
            except Exception:
                pass

            # If we have no counts but have a recommendation string, set a default
            if buy + hold + sell + strong_buy + strong_sell == 0 and recommendation:
                rec_lower = recommendation.lower()
                if "strong_buy" in rec_lower or "strongbuy" in rec_lower:
                    strong_buy = 1
                elif "buy" in rec_lower:
                    buy = 1
                elif "hold" in rec_lower:
                    hold = 1
                elif "sell" in rec_lower:
                    sell = 1

            result = {
                "buy": buy,
                "hold": hold,
                "sell": sell,
                "strong_buy": strong_buy,
                "strong_sell": strong_sell,
                "target_low": target_low if target_low and not np.isnan(target_low) else None,
                "target_mean": target_mean if target_mean and not np.isnan(target_mean) else None,
                "target_high": target_high if target_high and not np.isnan(target_high) else None,
                "target_median": target_median if target_median and not np.isnan(target_median) else None,
            }
            return result

        except Exception as exc:
            logger.warning(f"Error fetching analyst ratings for {ticker_symbol}: {exc}")
            return None

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
            # If the value is already a 2-letter code, return it uppercased
            if len(country_name.strip()) == 2:
                return country_name.strip().upper()
        return code
