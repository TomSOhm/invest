# 📊 Invest Solo

> Quantitative fundamental investment platform for PEA-eligible (French) and global stock analysis.

## What This Does

- **Screens** thousands of stocks using scientific valuation criteria
- **Scores** companies on a 0-100 composite scale (valuation, profitability, growth, health, risk)
- **Values** companies using DCF, Graham models, and relative valuation
- **Generates** Buy/Hold/Sell signals based on rigorous thresholds
- **Tracks** portfolios with risk metrics (Sharpe, VaR, drawdown)
- **Reports** daily market summaries and deep-dive company analyses

## Strategies

| Strategy | Universe | Constraints |
|----------|----------|-------------|
| **PEA** | EU/EEA headquartered companies | Long-only, no leverage, tax-optimized |
| **Global** | All publicly traded companies | Unconstrained, fundamental-driven |

## Quick Start

```bash
# Clone
git clone <repo-url>
cd invest

# Setup
cp config/.env.example config/.env
# Edit .env with your API keys

# Install
pip install -r requirements.txt

# Run daily analysis
python scripts/daily_run.py
```

## Key Files

- `docs/PROJECT_BRIEF.md` — Full project architecture & methodology
- `docs/METHODOLOGY.md` — Every formula & model explained
- `docs/PEA_RULES.md` — French PEA eligibility & tax rules
- `docs/DATA_SOURCES.md` — All APIs, libraries, MCP servers
- `config/settings.yaml` — All configurable parameters

## Tech Stack

Python 3.11+ · pandas · yfinance · FinanceToolkit · Plotly · Streamlit

## License

Private — Personal use only.
