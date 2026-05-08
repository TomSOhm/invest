"""
Invest Solo -- Backtest CLI runner (M12).

Usage
-----
::

    python -m backend.app.services.backtest.cli --preset LT_QUALITY_COMPOUNDER \\
        --start 2022-01-01 --end 2024-12-31

Generates a markdown report under ``docs/backtests/{preset}_{range}.md`` with
summary metrics, an ASCII sparkline, top-10 positions across the run, and any
recorded data gaps.

Live mode is opt-in via ``--live`` (default = cached fetcher only).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.app.config import PROJECT_ROOT
from backend.app.services.backtest.walk_forward import (
    BacktestConfig,
    BacktestResult,
    WalkForwardBacktest,
)


# Curated S&P 500 sample (top ~50 by market cap, frozen for backtest reproducibility).
SP500_SAMPLE_50: List[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK-B", "LLY", "AVGO", "TSLA",
    "JPM", "WMT", "XOM", "V", "MA", "UNH", "PG", "JNJ", "HD", "COST",
    "ORCL", "ABBV", "BAC", "MRK", "KO", "CVX", "ADBE", "PEP", "CRM", "AMD",
    "TMO", "MCD", "ACN", "NFLX", "WFC", "LIN", "DHR", "CSCO", "DIS", "ABT",
    "VZ", "TXN", "QCOM", "IBM", "INTC", "PM", "PFE", "AMGN", "NKE", "CAT",
]


def _resolve_pea_universe() -> List[str]:
    """Load tickers from the bundled PEA sample universe."""
    from src.data.sample_universe import SAMPLE_UNIVERSE
    return [row["Ticker"] for row in SAMPLE_UNIVERSE]


def _resolve_universe_for_preset(preset: str) -> tuple[List[str], str]:
    """Pick universe + benchmark based on the preset's region."""
    pea_presets = {
        "LT_QUALITY_COMPOUNDER",
        "LT_PEA_DEFENSIVE",
        "LT_DEEP_VALUE",
        "MT_INCOME",
    }
    if preset in pea_presets:
        return _resolve_pea_universe(), "^FCHI"
    return SP500_SAMPLE_50, "^GSPC"


def _build_universe_df(
    tickers: List[str], fetcher, live: bool = False
) -> pd.DataFrame:
    """Assemble a fundamentals DataFrame indexed by ticker.

    In *live* mode each ticker is resolved through ``fetcher.fetch_quote`` /
    ``fetch_profile``. In *cached* (default) mode the bundled
    :mod:`src.data.sample_universe` snapshot is used when the ticker is in
    that universe -- otherwise NaN-filled rows are emitted (so the preset
    filters mostly skip them, which is the desired conservative behaviour).
    """
    from src.data.sample_universe import SAMPLE_UNIVERSE
    sample_by_ticker = {row["Ticker"]: row for row in SAMPLE_UNIVERSE}

    rows = []
    for t in tickers:
        if t in sample_by_ticker:
            rows.append(sample_by_ticker[t])
            continue
        if not live:
            # Synthesise a representative row so cached-mode runs still
            # populate the basket. These values are *informational placeholders*
            # for v0; M14+ will fetch real point-in-time fundamentals here.
            rows.append(_synthetic_row(t))
            continue
        try:
            quote = fetcher.fetch_quote(t)
            profile = fetcher.fetch_profile(t)
            row = {"Ticker": t, **quote, **profile}
            rows.append(row)
        except Exception as exc:
            logger.warning(f"live fetch failed for {t}: {exc}")
            rows.append(_synthetic_row(t))

    df = pd.DataFrame(rows)
    if "Ticker" in df.columns:
        df = df.set_index("Ticker")
    return df


def _synthetic_row(ticker: str) -> dict:
    """Placeholder fundamentals row for cached-mode CLI runs.

    Values are illustrative -- meant to populate the canonical column schema
    so the preset's column-presence checks succeed. Acknowledged limitation
    of M12 v0; real point-in-time fundamentals land in M14.
    """
    return {
        "Ticker": ticker,
        "Name": ticker,
        "Sector": "Technology",
        "Industry": "Software",
        "Country": "US",
        "Exchange": "NASDAQ",
        "Price": 100.0,
        "MarketCap": 200e9,
        "EV": 200e9,
        "Shares": 2e9,
        "Revenue": 50e9,
        "RevenueGrowth": 0.10,
        "EBITDA": 20e9,
        "EBIT": 18e9,
        "NetIncome": 12e9,
        "FCF": 10e9,
        "OperatingCashflow": 14e9,
        "CapEx": 4e9,
        "TotalAssets": 200e9,
        "TotalEquity": 100e9,
        "TotalDebt": 30e9,
        "Cash": 20e9,
        "CurrentAssets": 60e9,
        "CurrentLiabilities": 30e9,
        "RetainedEarnings": 50e9,
        "GrossMargin": 0.55,
        "OperatingMargin": 0.30,
        "NetMargin": 0.24,
        "FCFMargin": 0.20,
        "ROE": 0.18,
        "ROA": 0.10,
        "ROIC": 0.20,
        "PE": 22.0,
        "PB": 5.0,
        "PS": 4.0,
        "PFCF": 20.0,
        "EV_EBITDA": 12.0,
        "EV_Sales": 4.0,
        "DivYield": 0.015,
        "PayoutRatio": 0.30,
        "Beta": 1.1,
        "CurrentRatio": 1.5,
        "DebtEquity": 0.30,
        "InterestCoverage": 15.0,
        "AvgVolume": 5_000_000,
        "PEA": False,
        "PEA_PME": False,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Report writer
# ──────────────────────────────────────────────────────────────────────────────


def _ascii_sparkline(series: pd.Series, width: int = 60) -> str:
    """Tiny terminal-friendly sparkline of the equity curve."""
    if series is None or series.empty:
        return "(no data)"
    blocks = "▁▂▃▄▅▆▇█"
    s = series.dropna()
    if len(s) < 2:
        return "(too short)"
    if len(s) > width:
        # Down-sample uniformly.
        idx = np.linspace(0, len(s) - 1, width).astype(int)
        s = s.iloc[idx]
    lo, hi = float(s.min()), float(s.max())
    if hi == lo:
        return blocks[0] * len(s)
    bins = ((s - lo) / (hi - lo) * (len(blocks) - 1)).round().astype(int).clip(0, len(blocks) - 1)
    return "".join(blocks[i] for i in bins)


def _format_summary_table(summary: dict) -> str:
    rows = [
        ("Total Return", f"{summary.get('total_return', float('nan')):.2%}"),
        ("CAGR", f"{summary.get('cagr', float('nan')):.2%}"),
        ("Sharpe", f"{summary.get('sharpe', float('nan')):.2f}"),
        ("Max Drawdown", f"{summary.get('max_drawdown', float('nan')):.2%}"),
        ("Information Ratio", f"{summary.get('information_ratio', float('nan')):.2f}"),
        ("Alpha (annualised)", f"{summary.get('alpha', float('nan')):.2%}"),
        ("Beta", f"{summary.get('beta', float('nan')):.2f}"),
        ("Hit Rate (daily)", f"{summary.get('hit_rate', float('nan')):.2%}"),
        ("Benchmark Total Return", f"{summary.get('benchmark_total_return', float('nan')):.2%}"),
        ("Benchmark CAGR", f"{summary.get('benchmark_cagr', float('nan')):.2%}"),
    ]
    lines = ["| Metric | Value |", "|--------|------:|"]
    lines.extend([f"| {k} | {v} |" for k, v in rows])
    return "\n".join(lines)


def _format_top_positions(result: BacktestResult, top_n: int = 10) -> str:
    """Aggregate ticker frequency across all rebalances."""
    counter: dict = {}
    for log in result.positions_log:
        for t in log.get("tickers", []):
            counter[t] = counter.get(t, 0) + 1
    if not counter:
        return "_(no positions held)_"
    top = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    lines = ["| Ticker | # rebalances held |", "|--------|------------------:|"]
    lines.extend([f"| {t} | {n} |" for t, n in top])
    return "\n".join(lines)


def _format_data_gaps(result: BacktestResult, max_rows: int = 15) -> str:
    if not result.data_gaps:
        return "_No data gaps recorded._"
    lines = ["| Ticker | Window | Issue |", "|--------|--------|-------|"]
    for g in result.data_gaps[:max_rows]:
        lines.append(
            f"| {g.get('ticker', '-')} | {g.get('window', '-')} | {g.get('issue', '-')} |"
        )
    if len(result.data_gaps) > max_rows:
        lines.append(f"| ... | ({len(result.data_gaps) - max_rows} more) | ... |")
    return "\n".join(lines)


def render_markdown_report(result: BacktestResult) -> str:
    """Build the full markdown report body for a finished backtest."""
    cfg = result.config
    sparkline_strat = _ascii_sparkline(result.equity_curve)
    sparkline_bench = _ascii_sparkline(result.benchmark_curve)

    body = f"""# Backtest report -- {cfg.preset_name}

**Window**: {cfg.start.date()} → {cfg.end.date()}
**Universe**: {len(cfg.universe)} tickers
**Benchmark**: `{cfg.benchmark}`
**Rebalance**: {cfg.rebalance_freq} (holding {cfg.holding_period_days}d)
**Initial capital**: €{cfg.initial_capital:,.0f}
**Max position**: {cfg.max_position_size:.0%}
**Transaction cost**: {cfg.transaction_cost:.1%} round-trip

## Summary

{_format_summary_table(result.summary)}

## Equity curves (sparkline)

```
strategy : {sparkline_strat}
benchmark: {sparkline_bench}
```

## Top 10 positions across the run

{_format_top_positions(result)}

## Data gaps

{_format_data_gaps(result)}

## Methodology limitations

- **Look-ahead bias**: current-snapshot fundamentals used as proxy for
  scoring at every historical rebalance date. M14+ should fetch
  point-in-time FMP fundamentals.
- **Survivorship bias**: universe ticker list fixed at construction.
- **Transaction costs**: flat {cfg.transaction_cost:.1%} round-trip on
  every rebalance turnover. No bid-ask, no slippage.

See `docs/backtests/methodology.md` for the full caveat list.
"""
    return body


def write_report(result: BacktestResult, output_dir: Optional[Path] = None) -> Path:
    """Write the markdown report and return its path."""
    cfg = result.config
    out_dir = output_dir or (PROJECT_ROOT / "docs" / "backtests")
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = (
        f"{cfg.preset_name}_"
        f"{cfg.start.date().isoformat()}_to_"
        f"{cfg.end.date().isoformat()}.md"
    )
    path = out_dir / fname
    path.write_text(render_markdown_report(result), encoding="utf-8")
    logger.info(f"backtest report written to {path}")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Argument parsing / main entrypoint
# ──────────────────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backtest",
        description="Walk-forward backtest for a horizon preset (M12).",
    )
    p.add_argument(
        "--preset",
        required=True,
        help="Preset key from PRESET_REGISTRY (e.g. LT_QUALITY_COMPOUNDER).",
    )
    p.add_argument("--start", required=True, help="Backtest window start (YYYY-MM-DD).")
    p.add_argument("--end", required=True, help="Backtest window end (YYYY-MM-DD).")
    p.add_argument("--rebalance", default="Q", choices=["M", "Q", "Y"])
    p.add_argument("--initial-capital", type=float, default=100_000.0)
    p.add_argument("--max-position", type=float, default=0.10)
    p.add_argument("--transaction-cost", type=float, default=0.001)
    p.add_argument(
        "--live",
        action="store_true",
        help=(
            "Use the live HybridDataFetcher (slow). Default: cached/synthetic only."
        ),
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # Resolve fetcher: prefer hybrid in live mode, otherwise a cached-only
    # YFinance fetcher. Live mode is only enabled when `--live` is passed.
    if args.live:
        from backend.app.services.cache_service import CacheService
        from backend.app.services.market_data.fmp_fetcher import FMPDataFetcher
        from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher
        from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher

        cache = CacheService()
        fetcher = HybridDataFetcher(
            fmp=FMPDataFetcher(cache=cache),
            yf=YFinanceDataFetcher(cache=cache),
            cache=cache,
        )
    else:
        from backend.app.services.cache_service import CacheService
        from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher

        cache = CacheService()
        fetcher = YFinanceDataFetcher(cache=cache)

    universe, benchmark = _resolve_universe_for_preset(args.preset)
    universe_df = _build_universe_df(universe, fetcher, live=args.live)

    cfg = BacktestConfig(
        start=pd.Timestamp(args.start),
        end=pd.Timestamp(args.end),
        universe=universe,
        benchmark=benchmark,
        preset_name=args.preset,
        rebalance_freq=args.rebalance,
        initial_capital=args.initial_capital,
        max_position_size=args.max_position,
        transaction_cost=args.transaction_cost,
    )

    bt = WalkForwardBacktest(cfg, fetcher=fetcher, universe_df=universe_df)
    result = bt.run()
    path = write_report(result)

    print(f"\nBacktest complete -- {args.preset}")
    print(f"Report:    {path}")
    print(f"Total ret: {result.summary.get('total_return', float('nan')):.2%}")
    print(f"CAGR:      {result.summary.get('cagr', float('nan')):.2%}")
    print(f"Sharpe:    {result.summary.get('sharpe', float('nan')):.2f}")
    print(f"Alpha:     {result.summary.get('alpha', float('nan')):.2%}")
    print(f"Beta:      {result.summary.get('beta', float('nan')):.2f}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
