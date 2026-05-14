"""Pydantic models for the company price-history endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChartPeriod = Literal["1M", "3M", "6M", "1Y", "5Y", "MAX"]


class Candle(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class ChartMetrics(BaseModel):
    total_return: float | None = Field(None, description="(last/first - 1) over the selected period")
    cagr: float | None = Field(None, description="Annualized compound growth, set only when period spans >= 1y")
    annualized_vol: float | None = Field(None, description="stdev(log_returns) * sqrt(252)")
    max_drawdown: float | None = Field(None, description="Peak-to-trough largest decline as negative fraction")
    beta: float | None = Field(
        None, description="cov(stock, benchmark) / var(benchmark); None when no benchmark or < 60 obs"
    )
    sharpe: float | None = Field(None, description="(mean - rf) / stdev * sqrt(252); rf=4% annual")


class MovingAverages(BaseModel):
    ma_50: list[float | None] = Field(default_factory=list, description="50d rolling mean of close, aligned to candles")
    ma_200: list[float | None] = Field(
        default_factory=list, description="200d rolling mean of close, aligned to candles"
    )


class PriceHistoryResponse(BaseModel):
    ticker: str
    period: ChartPeriod
    benchmark: str | None
    candles: list[Candle]
    benchmark_candles: list[Candle]
    metrics: ChartMetrics
    moving_averages: MovingAverages
