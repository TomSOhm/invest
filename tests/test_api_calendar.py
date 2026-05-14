"""HTTP-level tests for GET /api/company/{ticker}/calendar (sub-project 3).

Endpoint is yfinance-backed; ``source`` query param is honored for cache-key
isolation but routes the same way regardless of value.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.data_fetcher import DataFetcher


_STUB_CALENDAR = {
    "next_earnings_date": "2026-07-30",
    "next_earnings_eps_estimate": 2.10,
    "next_earnings_eps_low": 1.95,
    "next_earnings_eps_high": 2.20,
    "next_earnings_revenue_estimate": 93e9,
    "dividend_date": "2026-05-15",
    "ex_dividend_date": "2026-05-11",
    "dividend_amount": 0.27,
    "dividend_yield": 0.0046,
    "dividend_rate": 1.08,
    "dividends_5y": [
        {"ex_date": "2025-05-07", "amount": 0.26},
        {"ex_date": "2026-05-11", "amount": 0.27},
    ],
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_calendar_endpoint_returns_shape(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    def fake_fetch_calendar(
        self: DataFetcher,
        ticker: str,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        called["ticker"] = ticker
        called["source"] = source
        return _STUB_CALENDAR

    monkeypatch.setattr(DataFetcher, "fetch_calendar", fake_fetch_calendar, raising=False)

    resp = client.get("/api/company/AAPL/calendar?source=yfinance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_earnings_date"] == "2026-07-30"
    assert body["ex_dividend_date"] == "2026-05-11"
    assert body["dividend_amount"] == pytest.approx(0.27)
    assert len(body["dividends_5y"]) == 2
    assert called["ticker"] == "AAPL"
    assert called["source"] == "yfinance"


def test_calendar_endpoint_validates_ticker(client: TestClient) -> None:
    resp = client.get("/api/company/THIS_TICKER_IS_WAY_TOO_LONG/calendar")
    assert resp.status_code == 422
    assert "Invalid ticker" in resp.json()["detail"]


def test_calendar_endpoint_validates_source(client: TestClient) -> None:
    resp = client.get("/api/company/AAPL/calendar?source=bogus")
    assert resp.status_code == 422


def test_calendar_endpoint_default_source_is_hybrid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_fetch_calendar(
        self: DataFetcher,
        ticker: str,
        source: str = "hybrid",
    ) -> dict[str, Any]:
        captured["source"] = source
        return _STUB_CALENDAR

    monkeypatch.setattr(DataFetcher, "fetch_calendar", fake_fetch_calendar, raising=False)
    resp = client.get("/api/company/AAPL/calendar")
    assert resp.status_code == 200
    assert captured["source"] == "hybrid"
