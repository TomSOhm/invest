"""
Invest Solo -- Walk-Forward Backtest framework (M12).

At each rebalance date the framework:
    1. Scores the universe via ``score_dataframe`` (current-snapshot
       fundamentals + trailing-window price history for momentum).
    2. Applies the named horizon preset's filters via ``screen_horizon_preset``.
    3. Equal-weights the surviving names, capped at ``max_position_size``.
    4. Holds the resulting basket for ``holding_period_days`` calendar days,
       then re-evaluates.

Limitations of v0 (acknowledged):
- **Look-ahead bias**: current fundamentals are used as a proxy for the
  scoring snapshot at every historical rebalance date. M14+ should fetch the
  appropriate FMP quarterly fundamentals per date.
- **Survivorship bias**: the universe ticker list is fixed at construction;
  any name that has been delisted or had a corporate action mid-period is
  silently absent.
- **Transaction cost**: a flat 10 bp round-trip is debited on every
  rebalance turnover. No bid/ask, no slippage, no liquidity haircut.
- **Cash tracking**: the cash bucket of the portfolio is held flat (no
  interest), which is conservative when rates are low.

The framework gracefully tolerates **data gaps**: when a ticker has no price
history at a given date, it is excluded from the basket and a warning entry
is appended to ``BacktestResult.data_gaps``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.services.backtest.metrics import (
    alpha_beta,
    cagr,
    hit_rate,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    total_return,
)
from backend.app.services.market_data.protocol import MarketDataSource

# ──────────────────────────────────────────────────────────────────────────────
# Config / Result dataclasses
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class BacktestConfig:
    """Configuration for a single walk-forward backtest run.

    Attributes
    ----------
    start, end : pd.Timestamp
        Inclusive date window for the backtest.
    rebalance_freq : Literal["M", "Q", "Y"]
        Pandas freq alias for the rebalance grid (month-end / quarter-end /
        year-end). The first rebalance is the first such anchor on/after
        ``start``.
    holding_period_days : int
        Calendar days a basket is held before the next rebalance overrides
        it. Equal to one rebalance period for full-replacement strategies;
        smaller values are effectively ignored because the next rebalance
        flushes the basket anyway.
    universe : List[str]
        Tickers considered at every rebalance date.
    benchmark : str
        Single ticker fetched via ``MarketDataSource.fetch_price_history``;
        the daily total-return proxy is the price series itself (no
        dividends -- consistent with how individual names are handled).
    preset_name : str
        One of the keys in :data:`src.strategy.horizon_presets.PRESET_REGISTRY`.
    initial_capital : float, default 100_000
        Starting equity in EUR.
    max_position_size : float, default 0.10
        Per-name weight cap (0.10 = 10%).
    transaction_cost : float, default 0.001
        Flat round-trip cost charged on each rebalance turnover (10 bp).
    """

    start: pd.Timestamp
    end: pd.Timestamp
    universe: list[str]
    benchmark: str
    preset_name: str
    rebalance_freq: Literal["M", "Q", "Y"] = "Q"
    holding_period_days: int = 90
    initial_capital: float = 100_000.0
    max_position_size: float = 0.10
    transaction_cost: float = 0.001

    def __post_init__(self) -> None:
        # Normalise to pandas Timestamps so callers can pass strings.
        self.start = pd.Timestamp(self.start)
        self.end = pd.Timestamp(self.end)
        if self.end <= self.start:
            raise ValueError(f"BacktestConfig: end ({self.end}) must be > start ({self.start})")
        if self.rebalance_freq not in ("M", "Q", "Y"):
            raise ValueError(f"rebalance_freq must be 'M', 'Q', or 'Y' (got {self.rebalance_freq!r})")
        if self.max_position_size <= 0 or self.max_position_size > 1:
            raise ValueError(f"max_position_size must be in (0, 1] (got {self.max_position_size})")


@dataclass
class BacktestResult:
    """Output of :meth:`WalkForwardBacktest.run`."""

    config: BacktestConfig
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    positions_log: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, float] = field(default_factory=dict)
    data_gaps: list[dict[str, Any]] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Backtest engine
# ──────────────────────────────────────────────────────────────────────────────


class WalkForwardBacktest:
    """Walk-forward backtest engine -- preset-aware, cache-friendly.

    Parameters
    ----------
    config : BacktestConfig
    fetcher : MarketDataSource
        Any object that satisfies the protocol -- typically a
        ``HybridDataFetcher`` (cached) or a mock for unit tests.
    universe_df : pd.DataFrame, optional
        Pre-fetched fundamentals snapshot indexed by ticker. When omitted,
        the fetcher is asked for each ticker via ``fetch_quote`` /
        ``fetch_profile`` (slow). In test mode callers should always supply
        ``universe_df`` to keep runtime <30s.
    """

    def __init__(
        self,
        config: BacktestConfig,
        fetcher: MarketDataSource,
        universe_df: pd.DataFrame | None = None,
    ) -> None:
        self.config = config
        self.fetcher = fetcher
        self._universe_df = universe_df
        self._price_history_cache: dict[str, pd.DataFrame] = {}
        self._benchmark_history: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> BacktestResult:
        """Execute the backtest end-to-end and return a populated result."""
        cfg = self.config
        logger.info(
            f"Backtest: preset={cfg.preset_name} "
            f"window={cfg.start.date()}->{cfg.end.date()} "
            f"freq={cfg.rebalance_freq} universe={len(cfg.universe)}"
        )

        # 1. Pre-load price histories (cached per-ticker, reused for every rebalance).
        self._preload_price_histories()
        self._benchmark_history = self._fetch_history(cfg.benchmark)

        # 2. Build the rebalance schedule.
        rebalance_dates = self._build_rebalance_schedule()
        if not rebalance_dates:
            logger.warning("Backtest: no rebalance dates -- empty result")
            empty = pd.Series(dtype=float)
            return BacktestResult(
                config=cfg,
                equity_curve=empty,
                benchmark_curve=empty,
            )

        # 3. Score the universe ONCE (current-snapshot proxy -- M12 limitation).
        scored_df = self._score_universe()

        # 4. Walk forward.
        positions_log: list[dict[str, Any]] = []
        data_gaps: list[dict[str, Any]] = []

        # Daily equity curve, seeded with starting capital on the day BEFORE the
        # first rebalance. Use the trading-day index of the benchmark (which is
        # available for the full window) as the master clock so the strategy
        # and benchmark curves share an index.
        master_index = self._build_master_trading_index()
        if len(master_index) == 0:
            logger.warning("Backtest: empty trading index -- benchmark gap")
            empty = pd.Series(dtype=float)
            return BacktestResult(
                config=cfg,
                equity_curve=empty,
                benchmark_curve=empty,
                data_gaps=[{"date": None, "issue": "no benchmark price data"}],
            )

        equity = pd.Series(np.nan, index=master_index, dtype=float)
        equity.iloc[0] = cfg.initial_capital
        last_equity = cfg.initial_capital
        prev_basket_weights: dict[str, float] = {}

        for i, rebal_date in enumerate(rebalance_dates):
            # Pick the next master-index date >= rebal_date.
            anchor = master_index[master_index >= rebal_date]
            if len(anchor) == 0:
                continue
            anchor_date = anchor[0]

            # Determine the holding window: from this rebalance to the next
            # (or to ``end`` for the final block).
            if i + 1 < len(rebalance_dates):
                next_rebal = rebalance_dates[i + 1]
                window_end = master_index[master_index >= next_rebal]
                window_end = window_end[0] if len(window_end) > 0 else master_index[-1]
            else:
                window_end = master_index[-1]

            # Pick basket for this window using the preset.
            basket = self._build_basket(scored_df, anchor_date)

            # Cost of turnover relative to previous basket.
            turnover_cost = self._compute_turnover_cost(prev_basket_weights, basket)
            last_equity *= 1.0 - turnover_cost

            # Compute period returns per ticker over [anchor_date, window_end].
            period_returns, gaps = self._compute_basket_period_returns(basket, anchor_date, window_end, master_index)
            data_gaps.extend(gaps)

            # Apply the basket return path to equity.
            if not period_returns.empty:
                # Reweight: positions equal-weighted within basket.
                equity_path = (1.0 + period_returns).cumprod() * last_equity
                equity.loc[equity_path.index] = equity_path.values
                last_equity = float(equity_path.iloc[-1])
            else:
                # No data -> hold flat.
                window_slice = master_index[(master_index >= anchor_date) & (master_index <= window_end)]
                if len(window_slice) > 0:
                    equity.loc[window_slice] = last_equity

            positions_log.append(
                {
                    "rebalance_date": pd.Timestamp(anchor_date).date().isoformat(),
                    "n_positions": len(basket),
                    "tickers": list(basket.keys()),
                    "weights": dict(basket),
                    "turnover_cost": round(turnover_cost, 6),
                    "equity_after_costs": round(last_equity, 2),
                }
            )
            prev_basket_weights = basket

        # Forward-fill any missing equity points (idle days post-final rebalance).
        equity = equity.ffill().fillna(cfg.initial_capital)

        # 5. Build benchmark curve on the same master index.
        benchmark_curve = self._build_benchmark_curve(master_index)

        # 6. Compute summary metrics.
        summary = self._build_summary(equity, benchmark_curve)

        return BacktestResult(
            config=cfg,
            equity_curve=equity,
            benchmark_curve=benchmark_curve,
            positions_log=positions_log,
            summary=summary,
            data_gaps=data_gaps,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preload_price_histories(self) -> None:
        """Fetch price history for every ticker once and cache it locally."""
        for ticker in self.config.universe:
            if ticker in self._price_history_cache:
                continue
            try:
                hist = self._fetch_history(ticker)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"price history fetch failed for {ticker}: {exc}")
                hist = pd.DataFrame()
            self._price_history_cache[ticker] = hist

    def _fetch_history(self, ticker: str) -> pd.DataFrame:
        """Fetch and normalise OHLCV history -- index = DatetimeIndex (no tz)."""
        try:
            hist = self.fetcher.fetch_price_history(ticker, period="5y")
        except NotImplementedError:
            hist = pd.DataFrame()
        except Exception as exc:
            logger.warning(f"fetcher.fetch_price_history({ticker}) raised: {exc}")
            hist = pd.DataFrame()

        if hist is None or hist.empty:
            return pd.DataFrame()

        df = hist.copy()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
            df = df[~df.index.isna()].sort_index()
        # Strip timezone if present
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df

    def _build_rebalance_schedule(self) -> list[pd.Timestamp]:
        """Return rebalance anchor dates between start and end inclusive."""
        cfg = self.config
        # Use period_range for unambiguous quarter/month/year-end anchors.
        period_freq_map = {"M": "M", "Q": "Q", "Y": "Y"}
        freq = period_freq_map[cfg.rebalance_freq]
        periods = pd.period_range(start=cfg.start, end=cfg.end, freq=freq)
        anchors = [p.end_time.normalize() for p in periods]
        # Always include the start date as the first anchor so the first basket
        # gets a reasonable holding period (otherwise quarterly anchor is at
        # quarter-end which truncates the first window).
        anchors = [pd.Timestamp(cfg.start)] + [a for a in anchors if a > pd.Timestamp(cfg.start) and a <= cfg.end]
        return anchors

    def _build_master_trading_index(self) -> pd.DatetimeIndex:
        """Use the benchmark's trading-day index, restricted to [start, end]."""
        if self._benchmark_history is None or self._benchmark_history.empty:
            return pd.DatetimeIndex([])
        idx = self._benchmark_history.index
        cfg = self.config
        mask = (idx >= cfg.start) & (idx <= cfg.end)
        return idx[mask]

    # ------------------------------------------------------------------
    # Universe scoring
    # ------------------------------------------------------------------

    def _score_universe(self) -> pd.DataFrame:
        """Score the universe DataFrame via :func:`score_dataframe`.

        Uses the universe DataFrame the caller supplied (preferred). When
        absent, returns the input DataFrame unchanged (the preset will
        operate on whatever columns are present -- typically degenerate).
        """
        if self._universe_df is None or self._universe_df.empty:
            logger.warning(
                "WalkForwardBacktest: no universe_df supplied -- preset filters will see only sentinel columns"
            )
            return self._universe_df if self._universe_df is not None else pd.DataFrame()

        # Build the price-history map for momentum signals (M9).
        ph_map = {t: df for t, df in self._price_history_cache.items() if not df.empty}
        # Each ph_map entry needs a "Date" column for the momentum module.
        normalised_ph_map: dict[str, pd.DataFrame] = {}
        for t, df in ph_map.items():
            if df.empty:
                continue
            d = df.reset_index().rename(columns={"index": "Date"})
            if "Date" not in d.columns and "Date" not in d.iloc[:, 0].name.lower():
                d.columns = ["Date"] + list(d.columns[1:])
            normalised_ph_map[t] = d

        # Lazy import to keep this module import-light at package load.
        from src.analysis.scoring_engine import score_dataframe as _score_df

        try:
            scored = _score_df(
                self._universe_df,
                price_history_map=normalised_ph_map or None,
                market_history=self._benchmark_history.reset_index().rename(columns={"index": "Date"})
                if self._benchmark_history is not None and not self._benchmark_history.empty
                else None,
            )
        except Exception as exc:
            logger.warning(f"score_dataframe failed: {exc} -- using raw universe")
            scored = self._universe_df.copy()

        return scored

    def _build_basket(self, scored_df: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        """Apply the preset, equal-weight, and cap by ``max_position_size``."""
        from src.strategy.horizon_presets import screen_horizon_preset

        if scored_df is None or scored_df.empty:
            return {}

        try:
            screened = screen_horizon_preset(scored_df, self.config.preset_name)
        except KeyError:
            logger.error(f"unknown preset {self.config.preset_name!r} -- empty basket")
            return {}
        except Exception as exc:
            logger.warning(f"screen_horizon_preset raised: {exc} -- empty basket")
            return {}

        if screened is None or screened.empty:
            return {}

        # Cap by max_position_size: number of names = ceil(1 / max_position_size).
        max_n = max(1, int(round(1.0 / self.config.max_position_size)))
        # Filter out tickers with no price history at the rebalance date.
        eligible: list[str] = []
        for ticker in screened.index.tolist():
            hist = self._price_history_cache.get(ticker)
            if hist is None or hist.empty:
                continue
            if not (hist.index <= rebalance_date).any():
                continue
            eligible.append(ticker)
            if len(eligible) >= max_n:
                break

        if not eligible:
            return {}

        weight = min(self.config.max_position_size, 1.0 / len(eligible))
        return {t: weight for t in eligible}

    # ------------------------------------------------------------------
    # Period return computation
    # ------------------------------------------------------------------

    def _compute_basket_period_returns(
        self,
        basket: dict[str, float],
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        master_index: pd.DatetimeIndex,
    ):
        """Return a daily portfolio return series for the holding window.

        Returns
        -------
        (returns, gaps)
            returns : pd.Series indexed by trading-day Timestamps
            gaps    : list[dict] per-ticker missing-data warnings
        """
        gaps: list[dict[str, Any]] = []
        if not basket:
            return pd.Series(dtype=float), gaps

        window_idx = master_index[(master_index > start_date) & (master_index <= end_date)]
        if len(window_idx) == 0:
            return pd.Series(dtype=float), gaps

        ticker_returns: dict[str, pd.Series] = {}
        for ticker, _w in basket.items():
            hist = self._price_history_cache.get(ticker)
            if hist is None or hist.empty:
                gaps.append(
                    {
                        "ticker": ticker,
                        "window": (start_date.date().isoformat(), end_date.date().isoformat()),
                        "issue": "no price history",
                    }
                )
                continue
            close_col = self._pick_close_column(hist)
            if close_col is None:
                gaps.append(
                    {
                        "ticker": ticker,
                        "window": (start_date.date().isoformat(), end_date.date().isoformat()),
                        "issue": "no Close column",
                    }
                )
                continue
            # Reindex onto the master window to align with benchmark trading days.
            series = hist[close_col].reindex(hist.index.union(window_idx)).ffill().reindex(window_idx)
            if series.dropna().empty:
                gaps.append(
                    {
                        "ticker": ticker,
                        "window": (start_date.date().isoformat(), end_date.date().isoformat()),
                        "issue": "no overlap in window",
                    }
                )
                continue
            rets = series.pct_change().fillna(0.0)
            ticker_returns[ticker] = rets

        if not ticker_returns:
            return pd.Series(dtype=float), gaps

        # Equal-weight inside the basket. Weights from `basket` may be < 1/n
        # (because of max_position_size); the residual is implicit cash @ 0%.
        weights = pd.Series({t: basket[t] for t in ticker_returns})
        rets_df = pd.DataFrame(ticker_returns).fillna(0.0)
        portfolio_rets = rets_df.mul(weights, axis=1).sum(axis=1)
        # Cash bucket (residual weight) earns 0%.
        return portfolio_rets, gaps

    @staticmethod
    def _pick_close_column(df: pd.DataFrame) -> str | None:
        """Find the close-price column; tolerates Adj Close / Close variants."""
        for name in ("Adj Close", "AdjClose", "Close", "close"):
            if name in df.columns:
                return name
        return None

    def _compute_turnover_cost(self, prev: dict[str, float], curr: dict[str, float]) -> float:
        """Half the L1 distance × transaction cost rate."""
        if not prev and not curr:
            return 0.0
        all_names = set(prev) | set(curr)
        l1 = sum(abs(prev.get(t, 0.0) - curr.get(t, 0.0)) for t in all_names)
        # round-trip cost is on the buy side only of the change, so divide by 2.
        return float(l1 / 2.0 * self.config.transaction_cost)

    # ------------------------------------------------------------------
    # Benchmark + summary
    # ------------------------------------------------------------------

    def _build_benchmark_curve(self, master_index: pd.DatetimeIndex) -> pd.Series:
        """Normalised benchmark close series, rebased to initial_capital."""
        if self._benchmark_history is None or self._benchmark_history.empty:
            return pd.Series(dtype=float)
        close_col = self._pick_close_column(self._benchmark_history)
        if close_col is None:
            return pd.Series(dtype=float)
        bench = self._benchmark_history[close_col].reindex(master_index).ffill()
        if bench.dropna().empty:
            return pd.Series(dtype=float)
        first = float(bench.dropna().iloc[0])
        if first <= 0:
            return pd.Series(dtype=float)
        return bench / first * self.config.initial_capital

    def _build_summary(self, equity: pd.Series, benchmark: pd.Series) -> dict[str, float]:
        """Compute the full summary metric block."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            strat_rets = equity.pct_change().dropna()
            bench_rets = benchmark.pct_change().dropna() if not benchmark.empty else pd.Series(dtype=float)

            tr = total_return(equity)
            cagr_v = cagr(equity)
            sr = sharpe_ratio(strat_rets)
            mdd = max_drawdown(equity)
            ir = information_ratio(strat_rets, bench_rets)
            hr = hit_rate(strat_rets)
            alpha, beta = alpha_beta(strat_rets, bench_rets)

            bench_total = total_return(benchmark) if not benchmark.empty else float("nan")
            bench_cagr = cagr(benchmark) if not benchmark.empty else float("nan")

        return {
            "total_return": _round(tr, 4),
            "cagr": _round(cagr_v, 4),
            "sharpe": _round(sr, 3),
            "max_drawdown": _round(mdd, 4),
            "information_ratio": _round(ir, 3),
            "alpha": _round(alpha, 4),
            "beta": _round(beta, 3),
            "hit_rate": _round(hr, 4),
            "benchmark_total_return": _round(bench_total, 4),
            "benchmark_cagr": _round(bench_cagr, 4),
        }


def _round(value: float, ndigits: int) -> float:
    """nan-safe round; preserves nan as nan."""
    try:
        if pd.isna(value):
            return float("nan")
    except (TypeError, ValueError):
        return float("nan")
    return round(float(value), ndigits)
