"""HTTP-level tests for the ?source= query parameter on every relevant route."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.data_fetcher import DataFetcher


def _stub_company_row(ticker: str, effective_source: str = "hybrid") -> dict[str, Any]:
    return {
        "Ticker": ticker,
        "Name": "Stub",
        "Sector": "Tech",
        "Country": "US",
        "Exchange": "NMS",
        "Price": 1.0,
        "MarketCap": 1.0,
        "EV": 1.0,
        "Shares": 1.0,
        "PEA": False,
        "PEA_PME": False,
        "effective_source": effective_source,
        "source_fallback_message": None,
    }


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_company_detail_accepts_source(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    def fake_fetch_single(
        self: DataFetcher,
        ticker: str,
        cache_only: bool = False,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        called["source"] = source
        return _stub_company_row(ticker, effective_source=source)

    monkeypatch.setattr(DataFetcher, "fetch_single", fake_fetch_single)
    monkeypatch.setattr(
        DataFetcher,
        "fetch_analyst_ratings",
        lambda self, t, source="hybrid": None,
    )
    monkeypatch.setattr(
        "backend.app.services.company_service.screener_cache.lookup",
        lambda t: None,
    )

    resp = client.get("/api/company/AAPL?source=yfinance")
    assert resp.status_code == 200
    assert called["source"] == "yfinance"
    body = resp.json()
    assert body["data_source"] == "yfinance"
    assert body["effective_source"] == "yfinance"


def test_company_detail_rejects_unknown_source(client: TestClient) -> None:
    resp = client.get("/api/company/AAPL?source=bloomberg")
    assert resp.status_code == 422


def test_company_metrics_accepts_source(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        DataFetcher,
        "fetch_single",
        lambda self, t, cache_only=False, source="hybrid": _stub_company_row(t, source),
    )
    monkeypatch.setattr(
        DataFetcher,
        "fetch_analyst_ratings",
        lambda self, t, source="hybrid": None,
    )
    monkeypatch.setattr(
        "backend.app.services.company_service.screener_cache.lookup",
        lambda t: None,
    )

    resp = client.get("/api/company/AAPL/metrics?source=fmp")
    assert resp.status_code == 200


def test_company_horizon_rejects_bad_source(client: TestClient) -> None:
    resp = client.get("/api/company/AAPL/horizons/long_term?source=alpha")
    assert resp.status_code == 422


def test_watchlist_get_accepts_source(client: TestClient) -> None:
    resp = client.get("/api/watchlist/?source=yfinance")
    assert resp.status_code == 200


def test_watchlist_get_rejects_bad_source(client: TestClient) -> None:
    resp = client.get("/api/watchlist/?source=zzz")
    assert resp.status_code == 422


def test_portfolio_get_accepts_source(client: TestClient) -> None:
    resp = client.get("/api/portfolio/?source=fmp")
    assert resp.status_code == 200


def test_portfolio_get_rejects_bad_source(client: TestClient) -> None:
    resp = client.get("/api/portfolio/?source=foo")
    assert resp.status_code == 422


def test_price_history_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = {
        "ticker": "AAPL",
        "period": "1Y",
        "benchmark": None,
        "candles": [{"date": "2025-01-02", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1e6}],
        "benchmark_candles": [],
        "metrics": {
            "total_return": 0.1,
            "cagr": 0.1,
            "annualized_vol": 0.18,
            "max_drawdown": -0.1,
            "beta": None,
            "sharpe": 0.5,
        },
        "moving_averages": {"ma_50": [None], "ma_200": [None]},
    }
    from backend.app.services.chart_service import ChartService

    monkeypatch.setattr(
        ChartService,
        "get_price_history",
        lambda self, t, period, benchmark: fake,
    )

    resp = client.get("/api/company/AAPL/price-history?period=1Y")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["metrics"]["total_return"] == 0.1


def test_price_history_rejects_bad_period(client: TestClient) -> None:
    resp = client.get("/api/company/AAPL/price-history?period=10Y")
    assert resp.status_code == 422


def test_price_history_rejects_malformed_ticker(client: TestClient) -> None:
    # Over-length / illegal character: regex must fail-fast with 422.
    resp = client.get("/api/company/THIS_TICKER_IS_WAY_TOO_LONG/price-history?period=1Y")
    assert resp.status_code == 422


def test_price_history_rejects_unknown_benchmark(client: TestClient) -> None:
    resp = client.get("/api/company/AAPL/price-history?period=1Y&benchmark=^BAD")
    assert resp.status_code == 422


def test_price_history_accepts_known_benchmark(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.services.chart_service import ChartService

    monkeypatch.setattr(
        ChartService,
        "get_price_history",
        lambda self, t, period, benchmark: {
            "ticker": t,
            "period": period,
            "benchmark": benchmark,
            "candles": [],
            "benchmark_candles": [],
            "metrics": {
                "total_return": None,
                "cagr": None,
                "annualized_vol": None,
                "max_drawdown": None,
                "beta": None,
                "sharpe": None,
            },
            "moving_averages": {"ma_50": [], "ma_200": []},
        },
    )
    resp = client.get("/api/company/AAPL/price-history?period=1Y&benchmark=%5EGSPC")
    assert resp.status_code == 200
    assert resp.json()["benchmark"] == "^GSPC"
