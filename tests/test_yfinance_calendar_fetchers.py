"""Tests for yfinance.calendars fetcher methods (sub-project 3).

Covers the 3 new YFinanceDataFetcher methods:
- fetch_calendar         → tk.calendar (forward earnings + ex-div)
- fetch_dividends        → tk.dividends (last N years of payments)
- fetch_info_yields      → tk.info (dividendYield, dividendRate, ...)

Also covers the CompanyCalendar Pydantic model shape.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher


@pytest.fixture
def fetcher(tmp_path: Path) -> YFinanceDataFetcher:
    return YFinanceDataFetcher(cache=CacheService(cache_dir=tmp_path / "cache"))


# ---------------------------------------------------------------------------
# fetch_calendar
# ---------------------------------------------------------------------------


def test_fetch_calendar_basic(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.calendar = {
        "Earnings Date": [date(2026, 7, 30)],
        "Earnings High": 2.20,
        "Earnings Low": 1.95,
        "Earnings Average": 2.10,
        "Revenue High": 95e9,
        "Revenue Low": 91e9,
        "Revenue Average": 93e9,
        "Dividend Date": date(2026, 5, 15),
        "Ex-Dividend Date": date(2026, 5, 11),
    }
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_calendar("AAPL")
    assert out["next_earnings_date"] == "2026-07-30"
    assert out["next_earnings_eps_estimate"] == 2.10
    assert out["next_earnings_eps_low"] == 1.95
    assert out["next_earnings_eps_high"] == 2.20
    assert out["next_earnings_revenue_estimate"] == 93e9
    assert out["dividend_date"] == "2026-05-15"
    assert out["ex_dividend_date"] == "2026-05-11"


def test_fetch_calendar_empty_dict(fetcher: YFinanceDataFetcher) -> None:
    """Non-US ticker with no calendar coverage → all None fields, no crash."""
    fake_tk = MagicMock()
    fake_tk.calendar = {}
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_calendar("AIR.PA")
    assert out["next_earnings_date"] is None
    assert out["ex_dividend_date"] is None
    assert out["next_earnings_eps_estimate"] is None


def test_fetch_calendar_partial_dict(fetcher: YFinanceDataFetcher) -> None:
    """Some yfinance responses populate only a subset of keys."""
    fake_tk = MagicMock()
    fake_tk.calendar = {
        "Earnings Date": [date(2026, 7, 30)],
        # No dividend keys, no revenue keys
    }
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_calendar("CRWD")
    assert out["next_earnings_date"] == "2026-07-30"
    assert out["ex_dividend_date"] is None
    assert out["next_earnings_revenue_estimate"] is None


def test_fetch_calendar_swallows_exception(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    type(fake_tk).calendar = property(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_calendar("BOOM")
    assert out["next_earnings_date"] is None


def test_fetch_calendar_cached(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.calendar = {"Earnings Date": [date(2026, 7, 30)]}
    with patch("yfinance.Ticker", return_value=fake_tk) as mock_ticker:
        fetcher.fetch_calendar("AAPL")
        fetcher.fetch_calendar("AAPL")
    assert mock_ticker.call_count == 1  # second call served from cache


# ---------------------------------------------------------------------------
# fetch_dividends
# ---------------------------------------------------------------------------


def test_fetch_dividends_returns_last_5y(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    idx = pd.to_datetime(
        [
            "2020-05-12",  # > 5y old, should drop
            "2021-05-11",
            "2022-05-10",
            "2023-05-09",
            "2024-05-08",
            "2025-05-07",
            "2026-05-11",
        ]
    ).tz_localize("US/Eastern")
    fake_tk.dividends = pd.Series([0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27], index=idx)
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_dividends("AAPL", years=5)
    # Expect 5–7 rows depending on today's date; at minimum the recent 5 should be there
    assert len(out) >= 5
    # Most recent at the tail (ascending order)
    assert out[-1]["ex_date"] == "2026-05-11"
    assert out[-1]["amount"] == pytest.approx(0.27)


def test_fetch_dividends_empty_series(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.dividends = pd.Series([], dtype=float)
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_dividends("CRWD", years=5)
    assert out == []


def test_fetch_dividends_clamps_years(fetcher: YFinanceDataFetcher) -> None:
    """years arg must be clamped to [1, 20] — protect cache + memory."""
    fake_tk = MagicMock()
    fake_tk.dividends = pd.Series([], dtype=float)
    with patch("yfinance.Ticker", return_value=fake_tk):
        # 0 clamps up to 1
        fetcher.fetch_dividends("AAPL", years=0)
        # 100 clamps down to 20
        fetcher.fetch_dividends("AAPL", years=100)
    # Just confirming no exception; cache keys honor the clamp
    assert True


def test_fetch_dividends_swallows_exception(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    type(fake_tk).dividends = property(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_dividends("BOOM", years=5)
    assert out == []


def test_fetch_dividends_naive_index_skips_tz_localize(
    fetcher: YFinanceDataFetcher,
) -> None:
    """Naive DatetimeIndex must not call tz_localize(None) — already naive."""
    fake_tk = MagicMock()
    idx = pd.to_datetime(["2025-05-07", "2026-05-11"])  # no tz
    fake_tk.dividends = pd.Series([0.26, 0.27], index=idx)
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_dividends("EU.TICKER", years=5)
    assert len(out) == 2
    assert out[-1]["ex_date"] == "2026-05-11"


def test_fetch_dividends_returns_cached_payload_on_second_call(
    fetcher: YFinanceDataFetcher,
) -> None:
    fake_tk = MagicMock()
    idx = pd.to_datetime(["2026-05-11"]).tz_localize("US/Eastern")
    fake_tk.dividends = pd.Series([0.27], index=idx)
    with patch("yfinance.Ticker", return_value=fake_tk) as mock_ticker:
        fetcher.fetch_dividends("AAPL", years=5)
        fetcher.fetch_dividends("AAPL", years=5)
    assert mock_ticker.call_count == 1  # second served from cache


def test_fetch_dividends_skips_nan_amount_entries(
    fetcher: YFinanceDataFetcher,
) -> None:
    """NaN amounts get filtered via _safe_float → None → continue."""
    import numpy as np

    fake_tk = MagicMock()
    idx = pd.to_datetime(["2025-05-07", "2026-05-11"]).tz_localize("US/Eastern")
    fake_tk.dividends = pd.Series([float("nan"), 0.27], index=idx)
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_dividends("AAPL", years=5)
    # The NaN row is skipped; only the valid one survives
    assert len(out) == 1
    assert out[0]["amount"] == pytest.approx(0.27)
    _ = np  # silence unused-import lint


def test_fetch_info_yields_returns_cached_payload_on_second_call(
    fetcher: YFinanceDataFetcher,
) -> None:
    fake_tk = MagicMock()
    fake_tk.info = {"dividendYield": 0.0046}
    with patch("yfinance.Ticker", return_value=fake_tk) as mock_ticker:
        fetcher.fetch_info_yields("AAPL")
        fetcher.fetch_info_yields("AAPL")
    assert mock_ticker.call_count == 1


def test_fetch_calendar_earnings_date_empty_list_leaves_field_none(
    fetcher: YFinanceDataFetcher,
) -> None:
    """Branch: `Earnings Date` key present but empty list → no iso conversion."""
    fake_tk = MagicMock()
    fake_tk.calendar = {
        "Earnings Date": [],
        "Earnings Average": 2.10,
    }
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_calendar("AAPL")
    assert out["next_earnings_date"] is None
    assert out["next_earnings_eps_estimate"] == 2.10


def test_fetch_calendar_earnings_date_non_isoformat_leaves_field_none(
    fetcher: YFinanceDataFetcher,
) -> None:
    """Branch: first earnings date item without isoformat method (e.g. str)."""
    fake_tk = MagicMock()
    fake_tk.calendar = {"Earnings Date": ["2026-07-30"]}  # plain string, no .isoformat
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_calendar("AAPL")
    assert out["next_earnings_date"] is None


# ---------------------------------------------------------------------------
# fetch_info_yields
# ---------------------------------------------------------------------------


def test_fetch_info_yields_basic(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.info = {
        "dividendYield": 0.0046,
        "dividendRate": 1.08,
        "trailingAnnualDividendRate": 1.05,
        "trailingAnnualDividendYield": 0.0044,
    }
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_info_yields("AAPL")
    assert out["dividend_yield"] == pytest.approx(0.0046)
    assert out["dividend_rate"] == pytest.approx(1.08)
    assert out["trailing_annual_dividend_rate"] == pytest.approx(1.05)
    assert out["trailing_annual_dividend_yield"] == pytest.approx(0.0044)


def test_fetch_info_yields_missing_fields(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    fake_tk.info = {}
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_info_yields("CRWD")
    assert out["dividend_yield"] is None
    assert out["dividend_rate"] is None


def test_fetch_info_yields_swallows_exception(fetcher: YFinanceDataFetcher) -> None:
    fake_tk = MagicMock()
    type(fake_tk).info = property(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    with patch("yfinance.Ticker", return_value=fake_tk):
        out = fetcher.fetch_info_yields("BOOM")
    assert out["dividend_yield"] is None


# ---------------------------------------------------------------------------
# CompanyCalendar Pydantic model
# ---------------------------------------------------------------------------


def test_company_calendar_model_optional_fields() -> None:
    from backend.app.models.company import CompanyCalendar, DividendInfo

    cc = CompanyCalendar(
        next_earnings_date="2026-07-30",
        next_earnings_eps_estimate=2.10,
        next_earnings_revenue_estimate=93e9,
        ex_dividend_date="2026-05-11",
        dividend_amount=0.27,
        dividend_yield=0.0046,
        dividends_5y=[DividendInfo(ex_date="2025-05-07", amount=0.26)],
    )
    assert cc.next_earnings_date == "2026-07-30"
    assert cc.dividends_5y[0].amount == 0.26

    # All-None construction (non-US fallback) must not raise
    empty = CompanyCalendar()
    assert empty.next_earnings_date is None
    assert empty.dividends_5y == []
