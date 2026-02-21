"""
Invest Solo -- Data Fetcher Service
Fetches live data from yfinance and maps it to the exact column format
expected by scoring_engine.py.
"""
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from backend.app.config import settings
from backend.app.services.cache_service import CacheService


# The scoring engine expects these exact column names
SCORING_COLUMNS = [
    "PE", "PB", "PS", "PFCF", "EV_EBITDA", "EV_Sales",
    "ROE", "ROA", "ROIC", "OperatingMargin", "NetMargin", "FCFMargin", "GrossMargin",
    "RevenueGrowth", "CurrentRatio", "DebtEquity", "InterestCoverage",
    "DivYield", "PayoutRatio", "Beta",
    "Price", "MarketCap", "EV", "Shares",
    "Revenue", "EBITDA", "EBIT", "NetIncome", "FCF", "OperatingCashflow", "CapEx",
    "TotalAssets", "TotalEquity", "TotalDebt", "Cash",
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
        Missing fields are filled with np.nan.
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
            result["Revenue"] = _safe_get(info, "totalRevenue", np.nan)
            result["EBITDA"] = _safe_get(info, "ebitda", np.nan)
            result["EBIT"] = _safe_get(info, "ebitda", np.nan)  # yfinance often lacks EBIT separately
            result["NetIncome"] = _safe_get(info, "netIncomeToCommon", np.nan)

            # -- Cash Flow --
            result["OperatingCashflow"] = _safe_get(info, "operatingCashflow", np.nan)
            result["FCF"] = _safe_get(info, "freeCashflow", np.nan)
            capex_val = _safe_get(info, "operatingCashflow", 0) - _safe_get(info, "freeCashflow", 0)
            result["CapEx"] = capex_val if capex_val != 0 else np.nan

            # -- Balance Sheet --
            result["TotalAssets"] = _safe_get(info, "totalAssets", np.nan)
            result["TotalEquity"] = _safe_get(
                info, "totalStockholderEquity",
                _safe_get(info, "bookValue", np.nan)
                * _safe_get(info, "sharesOutstanding", 1)
                if _safe_get(info, "bookValue", None) is not None else np.nan
            )
            result["TotalDebt"] = _safe_get(info, "totalDebt", np.nan)
            result["Cash"] = _safe_get(info, "totalCash", np.nan)

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
            ebitda = _safe_get(info, "ebitda", np.nan)
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
            # ROIC: approximate as EBIT*(1-tax) / (Equity + Debt - Cash)
            ebit_val = _safe_get(info, "ebitda", np.nan)  # proxy
            equity = result["TotalEquity"]
            debt = result["TotalDebt"]
            cash = result["Cash"]
            if not any(np.isnan(x) if isinstance(x, float) else False for x in [ebit_val, equity, debt, cash]):
                invested_capital = equity + debt - cash
                if invested_capital > 0:
                    result["ROIC"] = (ebit_val * 0.75) / invested_capital  # 25% tax assumption
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

            # Interest coverage: approximate from ebitda / interest expense
            interest_expense = _safe_get(info, "totalDebt", 0) * 0.04  # rough 4% rate assumption
            if ebitda and not np.isnan(ebitda) and interest_expense > 0:
                result["InterestCoverage"] = ebitda / interest_expense
            else:
                result["InterestCoverage"] = np.nan

            # -- Shareholder --
            result["DivYield"] = _safe_get(info, "dividendYield", np.nan)
            result["PayoutRatio"] = _safe_get(info, "payoutRatio", np.nan)

            # -- Risk --
            result["Beta"] = _safe_get(info, "beta", np.nan)

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
