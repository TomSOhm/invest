# 📊 Invest Solo — Quantitative Fundamental Investment Platform

## Project Overview

**Owner:** Ohm-T (Hugging Face: `Ohm-T`)  
**Local Drive:** `E:\Projet_Solo\invest`  
**Future Git Repo:** To be linked  
**Primary Focus:** Scientific, rigorous stock valuation and portfolio strategy  
**Date Created:** 2026-02-16

---

## 🎯 Mission Statement

Build and maintain a **day-to-day investing strategy engine** powered by quantitative fundamental analysis:

1. **PEA Strategy** — French PEA-eligible values (EU/EEA headquartered companies, Euronext-listed, ETFs with ≥75% eligible equities)
2. **Global Strategy** — Unrestricted universe of any publicly traded companies worldwide
3. **Valuation Engine** — Scientific, rigorous metrics to characterize **undervalued** and **overvalued** potential of companies
4. **Daily Operations** — Actionable signals, watchlists, portfolio tracking, rebalancing alerts

---

## 🏗️ Project Architecture

```
E:\Projet_Solo\invest\
│
├── docs/                          # Documentation & research notes
│   ├── PROJECT_BRIEF.md           # This file — master reference
│   ├── METHODOLOGY.md             # Valuation methodology deep-dive
│   ├── PEA_RULES.md               # French PEA eligibility rules & constraints
│   ├── DATA_SOURCES.md            # All data providers, APIs, keys management
│   ├── METRICS_GLOSSARY.md        # Every metric used, formula, interpretation
│   └── CHANGELOG.md               # Project evolution log
│
├── config/                        # Configuration & environment
│   ├── .env.example               # Template for API keys (never commit real keys)
│   ├── settings.yaml              # Global settings (thresholds, weights, params)
│   ├── pea_universe.yaml          # PEA-eligible ticker universe
│   └── global_universe.yaml       # Global watchlist tickers
│
├── src/                           # Core Python source code
│   ├── __init__.py
│   ├── data/                      # Data acquisition layer
│   │   ├── __init__.py
│   │   ├── fetcher.py             # Unified data fetcher (yfinance, FMP, etc.)
│   │   ├── pea_eligibility.py     # PEA eligibility checker & universe builder
│   │   └── cache.py               # Local caching to avoid rate limits
│   │
│   ├── analysis/                  # Fundamental analysis engine
│   │   ├── __init__.py
│   │   ├── financial_health.py    # Liquidity, solvency, Altman Z-Score, Piotroski
│   │   ├── profitability.py       # ROE, ROA, ROIC, margins, DuPont decomposition
│   │   ├── growth.py              # Revenue/earnings growth, CAGR, trends
│   │   ├── valuation.py           # P/E, P/B, P/S, EV/EBITDA, PEG, DCF
│   │   ├── dcf_model.py           # Discounted Cash Flow implementation
│   │   ├── graham_model.py        # Benjamin Graham intrinsic value formula
│   │   ├── quality_score.py       # Composite quality scoring system
│   │   └── sector_comparison.py   # Relative valuation vs sector peers
│   │
│   ├── strategy/                  # Strategy & signal generation
│   │   ├── __init__.py
│   │   ├── screener.py            # Multi-criteria stock screener
│   │   ├── scoring.py             # Weighted composite scoring engine
│   │   ├── signals.py             # Buy/Hold/Sell signal generation
│   │   ├── pea_strategy.py        # PEA-specific strategy (tax optimization)
│   │   └── global_strategy.py     # Global unconstrained strategy
│   │
│   ├── portfolio/                 # Portfolio management
│   │   ├── __init__.py
│   │   ├── tracker.py             # Position tracking & P&L
│   │   ├── allocation.py          # Allocation optimizer (risk parity, etc.)
│   │   ├── rebalancer.py          # Rebalancing signals & scheduling
│   │   └── risk.py                # Risk metrics (VaR, Sharpe, drawdown)
│   │
│   └── reporting/                 # Output & visualization
│       ├── __init__.py
│       ├── daily_report.py        # Daily market summary & signals
│       ├── company_report.py      # Deep-dive single company analysis
│       ├── dashboard.py           # Interactive dashboard (Streamlit/React)
│       └── export.py              # Export to XLSX, PDF, DOCX
│
├── notebooks/                     # Jupyter notebooks for research
│   ├── 01_data_exploration.ipynb
│   ├── 02_valuation_backtesting.ipynb
│   ├── 03_pea_universe_analysis.ipynb
│   └── 04_strategy_development.ipynb
│
├── data/                          # Local data storage (gitignored)
│   ├── raw/                       # Raw API responses
│   ├── processed/                 # Cleaned & transformed data
│   ├── cache/                     # Temporary cache
│   └── exports/                   # Generated reports
│
├── tests/                         # Unit & integration tests
│   ├── test_fetcher.py
│   ├── test_valuation.py
│   ├── test_dcf.py
│   └── test_screener.py
│
├── scripts/                       # Utility scripts
│   ├── daily_run.py               # Daily analysis pipeline
│   ├── update_universe.py         # Refresh PEA/global universe
│   └── backtest.py                # Historical strategy backtesting
│
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── README.md
└── Makefile                       # Common commands shortcuts
```

---

## 📐 Valuation Methodology

### Core Valuation Models

| Model | Purpose | Key Inputs |
|-------|---------|------------|
| **DCF (Discounted Cash Flow)** | Intrinsic value from projected FCFs | FCF, WACC, Terminal Growth Rate |
| **Graham Number** | Conservative intrinsic value floor | EPS, BVPS |
| **Graham Growth Formula** | Growth-adjusted intrinsic value | EPS, Expected Growth Rate |
| **Relative Valuation** | Sector/peer comparison | P/E, P/B, EV/EBITDA vs peers |
| **DuPont Decomposition** | Profitability quality analysis | Margin × Turnover × Leverage |
| **Piotroski F-Score** | Financial strength (0-9) | 9 binary fundamental signals |
| **Altman Z-Score** | Bankruptcy risk assessment | 5 weighted financial ratios |

### Key Metrics Tracked

**Valuation Ratios:** P/E, Forward P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/Sales, PEG  
**Profitability:** ROE, ROA, ROIC, Gross Margin, Operating Margin, Net Margin, FCF Margin  
**Growth:** Revenue CAGR (3Y, 5Y), EPS CAGR, FCF Growth, Dividend Growth  
**Financial Health:** Current Ratio, Quick Ratio, D/E Ratio, Interest Coverage, FCF/Debt  
**Efficiency:** Asset Turnover, Inventory Turnover, Receivables Turnover  
**Shareholder Return:** Dividend Yield, Payout Ratio, Buyback Yield, Total Shareholder Yield  
**Quality Composite:** Custom weighted score combining all above categories

### Scoring System

Each company receives a **Composite Score (0-100)** based on weighted categories:

| Category | Weight | Description |
|----------|--------|-------------|
| Valuation Attractiveness | 25% | How cheap vs intrinsic value & peers |
| Financial Health | 20% | Balance sheet strength, solvency |
| Profitability Quality | 20% | Margins, returns on capital, consistency |
| Growth Trajectory | 15% | Revenue & earnings momentum |
| Shareholder Return | 10% | Dividends, buybacks, yield |
| Risk Assessment | 10% | Volatility, beta, Z-Score |

### Signal Generation

- **Strong Buy:** Score ≥ 80 AND Price < 70% of DCF intrinsic value
- **Buy:** Score ≥ 65 AND Price < 85% of DCF intrinsic value
- **Hold:** Score 40-65 OR Price within ±15% of intrinsic value
- **Sell:** Score < 40 OR Price > 130% of intrinsic value
- **Strong Sell:** Score < 25 OR Price > 150% of intrinsic value

---

## 🇫🇷 PEA-Specific Rules

### Eligibility Criteria
- Company **headquartered in EU or EEA** (European Economic Area)
- Listed on European exchanges (Euronext Paris, Amsterdam, Brussels, Lisbon, Dublin, Oslo, Milan)
- **ETFs eligible** if composed of ≥75% eligible equities
- REITs (SIICs) excluded since 2012 (but existing positions grandfathered)

### PEA Constraints
- **Maximum deposit:** €150,000 (PEA classique) + €225,000 (PEA-PME)
- **Tax advantage:** No capital gains tax after 5 years (only social charges 17.2%)
- **No short selling** within PEA
- **No leverage** (no margin)
- **Withdrawals before 5 years** → account closure + taxation

### PEA-PME Sub-Universe
- Companies with < 5,000 employees AND (Revenue < €1.5B OR Total Assets < €2B)
- Listed on Euronext Growth, Euronext Access, or meeting size criteria on main market
- Official list: [Euronext PEA-PME List](https://connect2.euronext.com/en/media/169)

---

## 🔧 Recommended Tools & Infrastructure

### Data Sources (Priority Order)

| Source | Type | Cost | Best For |
|--------|------|------|----------|
| **yfinance** | Python lib | Free | Quick data, price history, basic fundamentals |
| **Financial Modeling Prep (FMP)** | API | Freemium ($14/mo starter) | Full fundamentals, DCF, screener, global coverage |
| **Alpha Vantage** | API | Free (25 req/day) | Technical indicators, forex, crypto |
| **Finnhub** | API | Free tier | Real-time quotes, news, sentiment |
| **EODHD** | API | Freemium | EU coverage, fundamentals, dividends |
| **Euronext Web Services** | API | Paid | Official PEA eligibility, EU-specific data |
| **OpenBB** | Platform | Free/Open | Terminal alternative, integrates multiple sources |
| **FinanceToolkit** | Python lib | Free (needs FMP key) | Comprehensive ratios, DCF, DuPont analysis |

### MCP Servers (for Claude/AI integration)

| MCP Server | URL/Setup | Purpose |
|------------|-----------|---------|
| **Alpha Vantage MCP** | `https://mcp.alphavantage.co/mcp?apikey=KEY` | Real-time data, indicators |
| **Financial Datasets MCP** | `https://mcp.financialdatasets.ai/mcp` | Fundamentals, balance sheets |
| **Finance MCP (Yahoo)** | Local install via pip | Price data, basic analysis |
| **Daloopa MCP** | Already connected (`https://mcp.daloopa.com/server/mcp`) | Financial data extraction |

### Python Libraries

```
# Core
yfinance>=0.2.30
pandas>=2.0
numpy>=1.24
scipy>=1.11

# Financial Analysis
financetoolkit>=1.9
PyValuation>=0.1
openbb>=4.0
ta-lib  # Technical analysis (requires C library)

# Visualization
plotly>=5.18
streamlit>=1.30
matplotlib>=3.8

# Data & ML
scikit-learn>=1.3
statsmodels>=0.14
requests>=2.31
beautifulsoup4>=4.12

# Reports
python-docx>=1.0
openpyxl>=3.1
fpdf2>=2.7

# Utilities
pyyaml>=6.0
python-dotenv>=1.0
schedule>=1.2
loguru>=0.7
```

### Recommended MCP Connections (Claude.ai)

To maximize this project's potential, connect these MCPs in Claude settings:

1. **Alpha Vantage MCP** — Real-time financial data with 50+ endpoints
2. **Financial Datasets MCP** — SEC filings, balance sheets, income statements
3. **Daloopa MCP** ✅ Already connected — Financial data extraction
4. **Hugging Face MCP** ✅ Already connected — ML models for sentiment, NLP

---

## 📋 Agent Instructions (For Claude / AI Assistants)

### Context for Every Session

When working on this project, the AI assistant should:

1. **Always reference** `PROJECT_BRIEF.md` for architecture, methodology, and conventions
2. **Follow the folder structure** exactly as defined above
3. **Use the scoring system** (0-100 composite) for all stock evaluations
4. **Distinguish PEA vs Global** strategies — never suggest non-eligible stocks for PEA
5. **Cite data sources** — always mention which API/source was used for data
6. **Be quantitative** — include numbers, ratios, formulas in all analysis
7. **Flag limitations** — when data is stale, unavailable, or from free-tier sources
8. **Use French tax context** — PEA tax optimization, social charges, 5-year rule

### Standard Analysis Workflow

For any company analysis request:
1. Fetch latest financial data (income statement, balance sheet, cash flow)
2. Calculate all key metrics (valuation, profitability, growth, health)
3. Run DCF model with sensitivity analysis
4. Compare to sector peers (relative valuation)
5. Calculate Piotroski F-Score and Altman Z-Score
6. Generate composite score (0-100)
7. Determine signal (Strong Buy → Strong Sell)
8. Check PEA eligibility if relevant
9. Present findings with clear recommendation

### File Naming Conventions

- Analysis reports: `analysis_{TICKER}_{YYYY-MM-DD}.md`
- Screener results: `screener_{strategy}_{YYYY-MM-DD}.xlsx`
- Daily reports: `daily_report_{YYYY-MM-DD}.md`
- Backtest results: `backtest_{strategy}_{period}.md`

---

## 🚀 Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Set up project structure on `E:\Projet_Solo\invest`
- [ ] Initialize git repo
- [ ] Configure API keys (.env)
- [ ] Build data fetcher (yfinance + FMP)
- [ ] Implement basic financial metrics calculator
- [ ] Build PEA eligibility checker

### Phase 2: Analysis Engine (Week 3-4)
- [ ] Implement DCF model
- [ ] Implement Graham valuation models
- [ ] Build Piotroski F-Score calculator
- [ ] Build Altman Z-Score calculator
- [ ] Create DuPont decomposition
- [ ] Build composite scoring system
- [ ] Create relative valuation module

### Phase 3: Strategy & Screening (Week 5-6)
- [ ] Build multi-criteria screener
- [ ] Implement PEA-specific strategy
- [ ] Implement Global strategy
- [ ] Create signal generation logic
- [ ] Build daily screening pipeline

### Phase 4: Portfolio & Reporting (Week 7-8)
- [ ] Build portfolio tracker
- [ ] Implement risk metrics (VaR, Sharpe)
- [ ] Create allocation optimizer
- [ ] Build daily report generator
- [ ] Create company deep-dive report template
- [ ] Build interactive dashboard (Streamlit)

### Phase 5: Automation & ML (Month 3+)
- [ ] Schedule daily automated runs
- [ ] Add sentiment analysis (news, earnings calls)
- [ ] ML-based pattern recognition for quality scoring refinement
- [ ] Backtesting framework
- [ ] Connect MCP servers for real-time Claude analysis

---

## 📊 Key Decision Framework

### When to Buy (All must be true)
1. Composite Score ≥ 65
2. Price below estimated intrinsic value (DCF) by ≥15%
3. Piotroski F-Score ≥ 6
4. No significant red flags (fraud, accounting issues)
5. Positive or stable FCF trend

### When to Sell
1. Composite Score drops below 40
2. Price exceeds intrinsic value by >30%
3. Fundamental deterioration (declining margins, rising debt)
4. Better opportunity identified with same risk profile

### Position Sizing
- Max single position: 10% of portfolio
- Max sector exposure: 25% of portfolio
- Min positions for diversification: 15
- Cash reserve target: 5-15%

---

## 📎 Quick Reference Links

- [Euronext PEA-PME Eligible List](https://connect2.euronext.com/en/media/169)
- [PEA-eligible EEA Stocks (ProRealTime)](https://www.prorealtime.com/en/financial-instruments/pea-eligible-eee-stocks)
- [FinanceToolkit GitHub](https://github.com/JerBouma/FinanceToolkit)
- [Financial Modeling Prep API](https://financialmodelingprep.com/developer/docs)
- [Alpha Vantage API](https://www.alphavantage.co/documentation/)
- [Finnhub API](https://finnhub.io/docs/api)
- [yfinance docs](https://pypi.org/project/yfinance/)
- [Tidy Finance Python DCF](https://www.tidy-finance.org/python/discounted-cash-flow-analysis.html)
- [MCP Financial Datasets](https://docs.financialdatasets.ai/mcp-server)
