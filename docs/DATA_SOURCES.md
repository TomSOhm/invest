# 📡 Data Sources & API Reference

## Overview

This document catalogs all data sources, APIs, Python libraries, and MCP servers used in the project.

---

## Free Data Sources

### 1. yfinance (Python Library)
- **Install:** `pip install yfinance`
- **Cost:** Free (unofficial Yahoo Finance scraper)
- **Coverage:** Global stocks, ETFs, indices, crypto, forex
- **Data:** Price history, basic fundamentals, dividends, splits, options
- **Rate Limits:** ~2,000 requests/hour (unofficial, may break)
- **Strengths:** Easy to use, good for quick analysis, no API key needed
- **Weaknesses:** Unofficial API (can break), limited fundamental data depth, no financial statements detail
- **EU Coverage:** ✅ Euronext tickers use `.PA` (Paris), `.AS` (Amsterdam), `.BR` (Brussels), `.LS` (Lisbon)

```python
import yfinance as yf
# French stock example
total = yf.Ticker("TTE.PA")  # TotalEnergies on Euronext Paris
info = total.info
financials = total.financials
balance = total.balance_sheet
cashflow = total.cashflow
```

### 2. Alpha Vantage
- **URL:** https://www.alphavantage.co/
- **Cost:** Free (25 requests/day), Premium from $49.99/mo
- **API Key:** Required (free registration)
- **Coverage:** US stocks, some international, forex, crypto, commodities
- **Data:** Time series, fundamentals, technical indicators (50+), economic data
- **Strengths:** Rich technical indicator library, reliable, well-documented
- **Weaknesses:** Low free-tier limit, limited EU fundamental data
- **MCP Server:** `https://mcp.alphavantage.co/mcp?apikey=YOUR_KEY`

### 3. Finnhub
- **URL:** https://finnhub.io/
- **Cost:** Free tier (60 calls/min), Premium from $25/mo
- **API Key:** Required
- **Coverage:** Global stocks, forex, crypto
- **Data:** Real-time quotes, company news, SEC filings, sentiment, insider trading
- **Strengths:** Real-time data, news sentiment, IPO calendar
- **Weaknesses:** Limited historical fundamental data on free tier

### 4. OpenBB (Platform/SDK)
- **URL:** https://openbb.co/
- **Install:** `pip install openbb`
- **Cost:** Free (open source SDK)
- **Coverage:** Aggregates 30+ data sources
- **Data:** Everything — fundamentals, technicals, alternatives, macro, options
- **Strengths:** Unified interface to many sources, terminal-like experience
- **Weaknesses:** Complex setup, some sources need their own API keys

---

## Premium Data Sources

### 5. Financial Modeling Prep (FMP)
- **URL:** https://financialmodelingprep.com/
- **Cost:** Free (250 requests/day), Starter $14/mo, Professional $29/mo
- **API Key:** Required
- **Coverage:** Global (60,000+ symbols, 70+ exchanges)
- **Data:** Full financial statements, ratios, DCF, screener, ETF data, Euronext
- **Strengths:** Best value for comprehensive fundamentals, pre-built DCF, screener API
- **Weaknesses:** Some advanced features require paid plan
- **Used by:** FinanceToolkit library

```python
from financetoolkit import Toolkit
tk = Toolkit(["TTE.PA", "MC.PA"], api_key="FMP_KEY")
ratios = tk.ratios.collect_all_ratios()
dcf = tk.models.get_intrinsic_value()
```

### 6. EODHD
- **URL:** https://eodhd.com/
- **Cost:** Free tier (20 calls/day), from $19.99/mo
- **Coverage:** 70+ exchanges, strong EU/Euronext coverage
- **Data:** EOD prices, fundamentals, dividends, splits, bulk data, screener
- **Strengths:** Excellent EU market coverage, bulk download, dividends history
- **MCP Server:** Available (local install)

### 7. Financial Datasets
- **URL:** https://financialdatasets.ai/
- **Cost:** Paid (with free trial via OAuth)
- **Data:** Income statements, balance sheets, cash flow, prices, news
- **MCP Server:** `https://mcp.financialdatasets.ai/mcp` (OAuth) or API key version
- **Strengths:** Clean API, built for AI/LLM workflows

---

## Currently Connected MCP Servers

These are available in your Claude.ai environment right now:

| MCP | URL | Status |
|-----|-----|--------|
| **Daloopa** | `https://mcp.daloopa.com/server/mcp` | ✅ Connected |
| **Hugging Face** | `https://huggingface.co/mcp?login&gradio=none` | ✅ Connected |
| **Vibe Prospecting** | `https://vibeprospecting.explorium.ai/mcp` | ✅ Connected |

### Recommended Additional MCPs to Connect

1. **Alpha Vantage MCP** — Add in Claude settings → Integrations
   - URL: `https://mcp.alphavantage.co/mcp?apikey=YOUR_KEY`
2. **Financial Datasets MCP** — Add in Claude settings → Integrations
   - URL: `https://mcp.financialdatasets.ai/mcp`

---

## Euronext-Specific Data

### PEA Eligibility Lists
- **Euronext official PEA-PME list:** https://connect2.euronext.com/en/media/169
- **ProRealTime PEA list:** https://www.prorealtime.com/en/financial-instruments/pea-eligible-eee-stocks
- **RapidAPI Euronext PEA:** https://rapidapi.com/mgregori/api/euronext-pea-stocks-and-etfs

### Euronext Ticker Suffixes
| Exchange | Suffix | Example |
|----------|--------|---------|
| Paris | `.PA` | `TTE.PA` (TotalEnergies) |
| Amsterdam | `.AS` | `ASML.AS` |
| Brussels | `.BR` | `ABI.BR` (AB InBev) |
| Lisbon | `.LS` | `EDP.LS` |
| Dublin | `.IR` | `CRH.IR` |
| Oslo | `.OL` | `EQNR.OL` (Equinor) |
| Milan | `.MI` | `ENEL.MI` |

---

## API Key Management

### .env File Structure
```bash
# .env (NEVER commit this file)
ALPHA_VANTAGE_KEY=your_key_here
FMP_KEY=your_key_here
FINNHUB_KEY=your_key_here
EODHD_KEY=your_key_here
FINANCIAL_DATASETS_KEY=your_key_here
```

### Security Rules
1. **Never commit `.env`** — add to `.gitignore`
2. Use `python-dotenv` to load keys
3. Store backup of keys in password manager
4. Rotate keys if exposed
5. Use free tiers wisely — cache data locally to minimize API calls
