"""
Invest Solo -- Backtest package (M12).

Walk-forward backtest framework for validating horizon-preset signal alpha.

Public exports
--------------
``BacktestConfig``, ``BacktestResult``, ``WalkForwardBacktest`` from
:mod:`backend.app.services.backtest.walk_forward`. Pure-function metrics
helpers live in :mod:`backend.app.services.backtest.metrics`.

Limitations (v0)
----------------
- Uses **current-snapshot fundamentals** as a proxy for historical scoring at
  each rebalance date. Look-ahead bias is acknowledged. M14+ should fetch
  historical FMP fundamentals per quarter.
- Universe is **fixed at start**: delisted names not represented (survivorship
  bias). M14+ should source a point-in-time index membership history.
- Transaction costs are a flat **10 bp round-trip**; no slippage / spread.
- Sized for cached data only -- no live FMP/yfinance calls in the test path.
"""
from backend.app.services.backtest.walk_forward import (  # noqa: F401
    BacktestConfig,
    BacktestResult,
    WalkForwardBacktest,
)
from backend.app.services.backtest.metrics import (  # noqa: F401
    alpha_beta,
    cagr,
    hit_rate,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    total_return,
)

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "WalkForwardBacktest",
    "alpha_beta",
    "cagr",
    "hit_rate",
    "information_ratio",
    "max_drawdown",
    "sharpe_ratio",
    "total_return",
]
