# Backtest report -- LT_QUALITY_COMPOUNDER

**Window**: 2022-01-01 → 2024-12-31
**Universe**: 31 tickers
**Benchmark**: `^FCHI`
**Rebalance**: Q (holding 90d)
**Initial capital**: €100,000
**Max position**: 10%
**Transaction cost**: 0.1% round-trip

## Summary

| Metric | Value |
|--------|------:|
| Total Return | 0.00% |
| CAGR | 0.00% |
| Sharpe | nan |
| Max Drawdown | 0.00% |
| Information Ratio | -0.13 |
| Alpha (annualised) | nan% |
| Beta | nan |
| Hit Rate (daily) | 0.00% |
| Benchmark Total Return | 2.27% |
| Benchmark CAGR | 0.75% |

## Equity curves (sparkline)

```
strategy : ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
benchmark: ▅▅▄▄▃▄▃▂▃▁▁▂▃▂▂▁▂▃▃▃▄▅▅▅▄▅▆▆▅▅▅▆▅▅▅▅▄▅▅▆▆▆▇▇█▇▇█▇▆▆▅▆▆▇▆▆▅▆▆
```

## Top 10 positions across the run

_(no positions held)_

## Data gaps

_No data gaps recorded._

## Methodology limitations

- **Look-ahead bias**: current-snapshot fundamentals used as proxy for
  scoring at every historical rebalance date. M14+ should fetch
  point-in-time FMP fundamentals.
- **Survivorship bias**: universe ticker list fixed at construction.
- **Transaction costs**: flat 0.1% round-trip on
  every rebalance turnover. No bid-ask, no slippage.

See `docs/backtests/methodology.md` for the full caveat list.
