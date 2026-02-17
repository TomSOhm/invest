# 📐 Valuation Methodology — Scientific Framework

## Overview

This document details every valuation model, formula, and scientific criterion used in the Invest Solo platform. All models are grounded in academic finance literature and practitioner best practices.

---

## 1. Discounted Cash Flow (DCF) Model

### Theory
The intrinsic value of a company equals the present value of all its future free cash flows.

### Formula

```
Intrinsic Value = Σ [FCFₜ / (1 + WACC)ᵗ] + Terminal Value / (1 + WACC)ⁿ

Where:
  FCFₜ = Free Cash Flow in year t
  WACC = Weighted Average Cost of Capital
  n = projection period (typically 5-10 years)

Terminal Value = FCFₙ × (1 + g) / (WACC - g)
  g = terminal (perpetual) growth rate (typically 2-3%)

FCF = EBIT × (1 - Tax Rate) + D&A - CapEx - ΔWorking Capital

WACC = (E/V) × Re + (D/V) × Rd × (1 - Tc)
  Re = Cost of Equity (CAPM: Rf + β × Market Risk Premium)
  Rd = Cost of Debt (interest expense / total debt)
  E/V = Equity weight
  D/V = Debt weight
  Tc = Corporate tax rate
```

### Implementation Parameters
- **Projection period:** 10 years
- **Revenue growth assumptions:** Based on historical CAGR, analyst consensus, sector average
- **Operating margin:** Converge toward sector median over projection period
- **Terminal growth rate:** 2.5% default (GDP growth proxy)
- **Risk-free rate:** 10Y French OAT (PEA) or 10Y US Treasury (Global)
- **Equity risk premium:** 5.5% (Damodaran estimate)
- **Sensitivity analysis:** ±1% on WACC, ±0.5% on TGR → valuation matrix

### Quality Controls
- Compare DCF result to current market cap — flag if >3x deviation
- Run with optimistic/base/pessimistic scenarios
- Weight scenarios: 25% / 50% / 25%

---

## 2. Benjamin Graham Models

### Graham Number
Conservative floor for intrinsic value.

```
Graham Number = √(22.5 × EPS × BVPS)

Where:
  22.5 = Graham's constant (P/E of 15 × P/B of 1.5)
  EPS = Trailing twelve months earnings per share
  BVPS = Book value per share
```

### Graham Growth Formula
Adjusts for growth expectations.

```
Intrinsic Value = EPS × (8.5 + 2g) × 4.4 / Y

Where:
  8.5 = P/E base for zero-growth company
  g = expected annual growth rate (next 7-10 years), in %
  4.4 = average yield of AAA bonds when Graham wrote (constant)
  Y = current yield on AAA corporate bonds
```

### Graham Criteria (Defensive Investor)
A stock qualifies if ALL are met:
1. Adequate size: Revenue > €200M
2. Strong financial condition: Current ratio > 2.0
3. Earnings stability: Positive EPS in each of last 10 years
4. Dividend record: Uninterrupted dividends for ≥20 years
5. Earnings growth: Min 33% increase in EPS over last 10 years
6. Moderate P/E: P/E < 15 (based on 3-year average earnings)
7. Moderate P/B: P/B < 1.5 (or P/E × P/B < 22.5)

---

## 3. Piotroski F-Score (0–9)

Binary scoring system for financial strength:

| # | Signal | Criterion | Score |
|---|--------|-----------|-------|
| 1 | ROA | Net Income / Total Assets > 0 | +1 |
| 2 | CFO | Operating Cash Flow > 0 | +1 |
| 3 | ΔROA | ROA increased vs prior year | +1 |
| 4 | Accruals | CFO > Net Income (quality of earnings) | +1 |
| 5 | ΔLeverage | Long-term Debt/Assets decreased | +1 |
| 6 | ΔLiquidity | Current Ratio increased | +1 |
| 7 | Shares | No dilution (shares outstanding same or decreased) | +1 |
| 8 | ΔMargin | Gross Margin increased | +1 |
| 9 | ΔTurnover | Asset Turnover increased | +1 |

**Interpretation:** 8-9 = Strong, 5-7 = Moderate, 0-4 = Weak

---

## 4. Altman Z-Score

Bankruptcy risk prediction model:

```
Z-Score = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5

Where:
  X1 = Working Capital / Total Assets
  X2 = Retained Earnings / Total Assets
  X3 = EBIT / Total Assets
  X4 = Market Value of Equity / Total Liabilities
  X5 = Revenue / Total Assets
```

**Interpretation:**
- Z > 2.99 → Safe zone
- 1.81 < Z < 2.99 → Grey zone (uncertain)
- Z < 1.81 → Distress zone (high bankruptcy risk)

**Note:** For non-manufacturing companies, use the Z'-Score variant (different coefficients).

---

## 5. DuPont Decomposition

### 3-Factor DuPont
```
ROE = Net Profit Margin × Asset Turnover × Equity Multiplier
ROE = (Net Income / Revenue) × (Revenue / Total Assets) × (Total Assets / Equity)
```

### 5-Factor Extended DuPont
```
ROE = Tax Burden × Interest Burden × EBIT Margin × Asset Turnover × Equity Multiplier
    = (NI/EBT) × (EBT/EBIT) × (EBIT/Revenue) × (Revenue/Assets) × (Assets/Equity)
```

**Purpose:** Identifies the *source* of returns — margin-driven vs leverage-driven vs efficiency-driven.

---

## 6. Relative Valuation Metrics

### Valuation Ratios & Interpretation

| Metric | Formula | "Cheap" Signal | "Expensive" Signal |
|--------|---------|----------------|-------------------|
| P/E | Price / EPS | < Sector median × 0.7 | > Sector median × 1.3 |
| Forward P/E | Price / Estimated EPS | < 12 (value) | > 25 (growth premium) |
| P/B | Price / Book Value per Share | < 1.0 (deep value) | > 5.0 |
| P/S | Price / Sales per Share | < 1.0 | > 10.0 |
| P/FCF | Price / Free Cash Flow per Share | < 15 | > 40 |
| EV/EBITDA | Enterprise Value / EBITDA | < 8 | > 20 |
| EV/Sales | Enterprise Value / Revenue | < 1.5 | > 10 |
| PEG | (P/E) / EPS Growth Rate | < 1.0 (undervalued growth) | > 2.0 |

### Sector-Relative Z-Score
```
Z_metric = (Company_metric - Sector_median) / Sector_std_dev

If Z < -1.5 → Significantly undervalued on this metric
If Z > +1.5 → Significantly overvalued on this metric
```

---

## 7. Quality & Moat Assessment

### Quality Indicators
- **Consistent Margins:** StdDev of operating margin < 5% over 5 years
- **Earnings Quality:** CFO/Net Income > 1.0 consistently
- **Capital Allocation:** ROIC > WACC (creates value)
- **Revenue Diversification:** No single customer > 20% of revenue
- **Competitive Position:** Stable or growing market share

### Economic Moat Signals
- Gross margin > 40% (pricing power)
- ROIC > 15% sustained over 5+ years
- Switching costs (SaaS retention > 90%)
- Network effects (user growth ↔ value growth)
- Intangible assets (brands, patents, licenses)

---

## 8. Risk Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| Beta | Covariance(stock, market) / Var(market) | 0.5–1.5 |
| Sharpe Ratio | (Return - Rf) / StdDev | > 1.0 |
| Max Drawdown | Peak-to-trough decline | < 30% |
| Value at Risk (95%) | 5th percentile of return distribution | Monitor |
| Debt/Equity | Total Debt / Equity | < 1.0 preferred |
| Interest Coverage | EBIT / Interest Expense | > 5x |

---

## 9. Composite Scoring Formula

```python
def composite_score(company):
    scores = {
        'valuation': valuation_score(company) * 0.25,      # 0-100
        'financial_health': health_score(company) * 0.20,    # 0-100
        'profitability': profit_score(company) * 0.20,       # 0-100
        'growth': growth_score(company) * 0.15,              # 0-100
        'shareholder_return': return_score(company) * 0.10,  # 0-100
        'risk': risk_score(company) * 0.10,                  # 0-100
    }
    return sum(scores.values())
```

Each sub-score maps metrics to a 0-100 scale using percentile ranks within the relevant universe (PEA or Global).
