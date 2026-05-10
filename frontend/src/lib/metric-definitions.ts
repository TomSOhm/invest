// Single source of truth for in-app metric definitions.
// Keyed by stable metric ID. Used by `MetricInfo.tsx`.
//
// Writing convention:
//   - what / why / goodVsBad / example: 1-3 plain-English sentences each
//   - PEA-French-investor context where relevant
//   - Numeric thresholds match the v2 scoring engine (M0-M13)

export interface MetricDef {
  label: string;
  what: string;
  why: string;
  goodVsBad: string;
  example: string;
  caveats?: string;
  reference?: string;
  formula?: string;
}

export const METRIC_DEFINITIONS: Record<string, MetricDef> = {
  // ============================================================
  // Composite / horizon scores and signals
  // ============================================================
  score_lt: {
    label: "Long-Term Score (LT, 0-100)",
    formula: "\\text{score}_{LT} = \\sum_{k} w_{LT,k} \\cdot \\text{subscore}_{k}, \\quad k \\in \\{\\text{val}, \\text{prof}, \\text{health}, \\text{EQ}, \\text{growth}, \\text{share}, \\text{risk}\\}",
    what:
      "Composite score for a buy-and-hold horizon (5+ years). Weighted average of valuation (20%), profitability (25%), financial health (15%), earnings quality (10%), growth (10%), capital allocation (10%) and risk (10%).",
    why:
      "Identifies durable compounders worth holding through cycles. The weighting prioritises quality and balance-sheet strength over short-term momentum.",
    goodVsBad:
      "≥80 Strong Buy candidate (when DCF MoS also ≥30%). 65-80 Buy candidate. 40-65 Hold. <40 Sell. <25 Strong Sell.",
    example:
      "Hermès (RMS.PA) typically scores 75-85 LT thanks to high ROIC and clean accruals. A struggling cyclical like Atos (ATO.PA) scores 25-35 LT because Altman Z is in distress.",
    caveats:
      "A high LT score is necessary but not sufficient: the gates check (passes_gates_lt) must also pass, and DCF MoS must align before a Strong Buy can fire.",
  },
  score_mt: {
    label: "Medium-Term Score (MT, 0-100)",
    formula: "\\text{score}_{MT} = \\sum_{k} w_{MT,k} \\cdot \\text{subscore}_{k}",
    what:
      "Composite score for a 6-24 month horizon. Same building blocks as LT but adds 10% weight on momentum and lowers profitability/quality weights.",
    why:
      "Captures GARP-style and turnaround setups where catalysts (EPS revisions, margin trends) matter more than 10-year compound stories.",
    goodVsBad:
      "≥65 Buy candidate when momentum + EPS revisions confirm. 40-65 Hold. <40 Sell.",
    example:
      "ASML.AS during a positive EPS-revision cycle can move from LT 60 to MT 72. A stalling defensive like Nestlé typically MT 40-50.",
    caveats:
      "MT scoring requires recent price-history data; tickers with sparse cache may show NaN momentum components and degrade to a quality-only proxy.",
  },
  score_st: {
    label: "Short-Term Score (ST, 0-100)",
    formula: "\\text{score}_{ST} = \\sum_{k} w_{ST,k} \\cdot \\text{subscore}_{k}",
    what:
      "Composite score for a <6 month horizon. 55% weight on momentum, 10% risk, smaller contributions from valuation/quality. Designed for tactical trades.",
    why:
      "Identifies post-earnings drift, breakout, or oversold-bounce setups. Quality acts as a floor, momentum as the engine.",
    goodVsBad:
      "≥50 considered tradable. ≥70 strong setup. <40 avoid. ST always pairs with passes_gates_st (volume, distress, vol caps).",
    example:
      "NVDA after a SUE z-score of +2.3 with golden-cross may score ST 78. A low-volume European mid-cap will score ST 30 because liquidity gates fail.",
    caveats:
      "Short-term trading is sub-optimal in a PEA wrapper (30% PFU before 5y). The recommended_account flag will read 'CTO' for ST setups.",
  },
  signal: {
    label: "Investment Signal",
    what:
      "Discrete recommendation derived from the horizon's composite score combined with DCF Margin of Safety (MoS).",
    why:
      "Translates a 0-100 score plus a price-to-intrinsic ratio into one of five actions: Strong Buy / Buy / Hold / Sell / Strong Sell.",
    goodVsBad:
      "Strong Buy = score≥80 AND MoS≥30%. Buy = score≥65 AND MoS≥15%. Hold = neither side triggered. Sell = score≤40 OR MoS≤-15%. Strong Sell = MoS≤-30%.",
    example:
      "MC.PA at €600 with score 72 and MoS +18% → Buy. Same name at €900 with score 68 but MoS -22% → Sell because price overshot intrinsic value.",
    caveats:
      "When DCF cannot compute (banks, REITs, NaN inputs) the signal degrades gracefully to composite-only thresholds.",
  },
  passes_gates: {
    label: "Passes Gates",
    what:
      "Boolean flag: does the ticker pass every hard filter required by this horizon (data completeness, distress check, liquidity, market cap, etc.)?",
    why:
      "A high score on a ticker that fails gates is meaningless: the engine refuses to recommend it. Gates protect against value traps and dead universe entries.",
    goodVsBad:
      "True = all gates clear, score is reliable. False = at least one gate failed; check the blockers list to know which.",
    example:
      "ATOS.PA passes_gates_lt = false because data_completeness < 0.7 (delisted). META passes_gates_lt = true.",
  },
  blockers: {
    label: "Blockers",
    what:
      "List of gate keys that failed for this horizon. Each entry is a short label like 'min_data_completeness', 'max_distress', 'min_avg_volume'.",
    why:
      "Tells you exactly why a name didn't pass — whether the data is too sparse, the company is in distress, the stock is too thinly traded, etc.",
    goodVsBad:
      "Empty list = ticker is investable at this horizon. Non-empty list = work to do (better data) or investment thesis incompatible with the gate.",
    example:
      "['max_distress', 'min_data_completeness'] on a fading small cap means it failed both the Altman floor and had too many missing fundamentals.",
  },
  recommended_account: {
    label: "Recommended Account",
    what:
      "Whether this horizon's setup is best held in a PEA (Plan d'Épargne en Actions) or CTO (compte-titres ordinaire).",
    why:
      "PEA offers tax-advantaged compounding (17.2% social charges only after 5y). CTO has 30% flat tax but no holding-period or geography restrictions.",
    goodVsBad:
      "PEA = long-term setups on EU/EEA equities. CTO = short-term trades, US equities, or non-PEA-eligible markets.",
    example:
      "LT_QUALITY_COMPOUNDER on RMS.PA → PEA. ST_MOMENTUM on NVDA → CTO (US ticker, also short horizon).",
    caveats:
      "Not all PEA-eligible stocks should be held in PEA: high-turnover trades hit the 30% PFU and lose the wrapper's benefit.",
  },

  // ============================================================
  // DCF
  // ============================================================
  dcf_fair_value: {
    label: "DCF Fair Value (low / mid / high)",
    formula: "\\text{Fair Value} = \\sum_{t=1}^{n} \\dfrac{FCF_t}{(1+WACC)^t} + \\dfrac{TV}{(1+WACC)^n}, \\quad TV = \\dfrac{FCF_n \\cdot (1+g)}{WACC - g}",
    what:
      "Per-share intrinsic value from a 2-stage DCF (5-year explicit projection + Gordon terminal value), discounted at WACC. Three estimates form a sensitivity range from the WACC ±1pp × terminal-growth ±50bp grid.",
    why:
      "Anchors the price you are willing to pay. Compared against current market price to derive Margin of Safety.",
    goodVsBad:
      "Mid is the base case. Low / high give you a band: if current price is below 'low', the stock looks deeply undervalued across reasonable assumptions. Above 'high' = expensive.",
    example:
      "AAPL at $190 with FV range $150-$170-$200 → mid says fairly priced; low/high range straddles current price → fair zone.",
    caveats:
      "DCF is unreliable for financials (no FCF margin), early-stage growth (high terminal-rate sensitivity), and any ticker missing 5y of FCF history.",
  },
  dcf_mos: {
    label: "DCF Margin of Safety (MoS)",
    formula: "MoS = \\dfrac{\\text{Fair Value} - \\text{Price}}{\\text{Price}}",
    what:
      "Percentage gap between DCF fair value and current price: MoS = (fair_value - price) / price.",
    why:
      "Quantifies discount/premium vs intrinsic value. The signal engine reads MoS to gate Buy and Sell verdicts.",
    goodVsBad:
      "≥30% Strong Buy candidate. 15-30% Buy. -15% to +15% Hold. -30% to -15% Sell. ≤-30% Strong Sell.",
    example:
      "BRK-B with FV $480 and price $450 → MoS +6.7%. AAPL with FV $150 and price $190 → MoS -21% (sell territory).",
    caveats:
      "MoS is NaN when DCF inputs are insufficient. In that case the signal falls back to composite-only thresholds.",
  },
  wacc_used: {
    label: "WACC (Weighted Average Cost of Capital)",
    formula: "WACC = \\dfrac{E}{V} R_e + \\dfrac{D}{V} R_d (1 - T_c), \\quad R_e = R_f + \\beta \\cdot ERP",
    what:
      "Discount rate used in the DCF. WACC = (E/V)·Re + (D/V)·Rd·(1-Tc) where Re comes from CAPM (Rf + Beta·ERP) and Rd is a cost-of-debt assumption.",
    why:
      "The hurdle rate. Higher WACC compresses fair value; lower WACC inflates it.",
    goodVsBad:
      "There is no good/bad — context matters. Range 7-12% is typical for established equities. <6% suggests low beta + low debt; >14% suggests cyclical or distressed.",
    example:
      "AAPL ≈ 9% WACC, Nestlé ≈ 6.5%, a junior miner ≈ 14%.",
    caveats:
      "Sensitivity grid varies WACC ±1pp on top of this base value.",
  },

  // ============================================================
  // Earnings quality
  // ============================================================
  piotroski_f: {
    label: "Piotroski F-Score (0-9)",
    formula: "F = \\sum_{i=1}^{9} \\mathbb{1}[\\text{signal}_i \\text{ triggers}]",
    what:
      "Sum of 9 binary signals derived from year-over-year deltas: ROA>0, CFO>0, ΔROA>0, CFO>NI, ΔLeverage<0, ΔCurrent ratio>0, no dilution (Δshares ≤ +0.5%), ΔGross margin>0, ΔAsset turnover>0.",
    why:
      "A pure quality signal. Joseph Piotroski showed in 2000 that high-F-Score names beat low-F-Score names by 7.5% annualised in the value universe.",
    goodVsBad:
      "9 = perfect quality. 7-8 = strong, qualifies for LT_QUALITY_COMPOUNDER. 5-6 = mixed. ≤4 = improving but unproven. 0-2 = deteriorating fundamentals.",
    example:
      "MSFT and GOOGL routinely score 9. A turnaround name posting first profits may move from 3 to 7 in a year.",
    caveats:
      "Signals with missing inputs are skipped, so a score of 6 from 7 evaluated signals is different from 6 from 9 evaluated signals — check data_completeness.",
  },
  altman_z: {
    label: "Altman Z'' Score",
    formula: "Z'' = 6.56\\,X_1 + 3.26\\,X_2 + 6.72\\,X_3 + 1.05\\,X_4",
    what:
      "Bankruptcy-risk score combining working capital, retained earnings, EBIT, equity-to-liabilities. We use the Z'' variant (no asset-turnover X5) for non-manufacturers; classic Z with X5 for manufacturers.",
    why:
      "Predicts financial distress. Edward Altman's models flag bankruptcy 1-2 years out with ~80% accuracy in the original 1968 study.",
    goodVsBad:
      "Z'' Safe >2.6, Grey 1.1-2.6, Distress <1.1. Classic Z thresholds: Safe >2.99, Grey 1.81-2.99, Distress <1.81.",
    example:
      "Nestlé Z'' ≈ 4 (Safe). Atos pre-restructuring Z'' ≈ -0.8 (deep Distress). NVDA Z'' often >100 because near-zero net debt.",
    caveats:
      "Banks and insurers (BNP, JPM) lack the working-capital concept and return Z = NaN. Real estate is also a poor fit.",
  },
  altman_zone: {
    label: "Altman Distress Zone",
    what:
      "Categorical mapping of Altman Z to: Safe, Grey, or Distress.",
    why:
      "Quick read for non-finance users. The screener's not_in_distress universal pre-filter excludes Distress names.",
    goodVsBad:
      "Safe: bankruptcy unlikely in next 1-2 years. Grey: ambiguous, monitor. Distress: high probability of financial trouble.",
    example:
      "Nestlé = Safe. ATO.PA = Distress. Cyclical industrial near trough = Grey.",
  },
  m_score: {
    label: "Beneish M-Score",
    formula: "M = -4.84 + 0.920\\,DSRI + 0.528\\,GMI + 0.404\\,AQI + 0.892\\,SGI + 0.115\\,DEPI - 0.172\\,SGAI + 4.679\\,TATA - 0.327\\,LVGI",
    what:
      "8-variable model that flags earnings manipulation. Combines days-sales-in-receivables, gross margin, asset quality, sales growth, depreciation, SG&A, leverage, and accruals.",
    why:
      "Catches aggressive accounting before it shows up in restatements. Beneish 1999 detected 76% of manipulators.",
    goodVsBad:
      "M < -2.22 = clean. -2.22 to -1.78 = monitor. M > -1.78 = manipulation likely.",
    example:
      "Berkshire's M-Score is typically -2.5 (clean). Enron in 2001 had M > -1.78 well before collapse.",
    caveats:
      "Sensitive to acquisition-driven growth and one-off items. Confirm flags with deeper accounting review.",
  },
  sloan_accruals: {
    label: "Sloan Accruals Ratio",
    formula: "\\text{Sloan Accruals} = \\dfrac{NI - CFO}{\\overline{\\text{Total Assets}}}",
    what:
      "(Net Income - CFO) / Average Total Assets. Measures how much of reported earnings is accrual-based rather than cash.",
    why:
      "Sloan 1996 showed that low-accrual stocks beat high-accrual stocks by ~10% annualised. High accruals signal lower earnings persistence.",
    goodVsBad:
      "<0.05 strong. 0.05-0.10 normal. 0.10-0.20 aggressive. >0.20 red flag.",
    example:
      "Microsoft typically <0.05. A growth-by-acquisition roll-up may post 0.18 (aggressive).",
    caveats:
      "Capex-heavy industries (telcos, utilities) naturally run higher accruals; compare within sector.",
  },
  cash_conversion_ratio_5y: {
    label: "Cash Conversion Ratio (5y avg)",
    formula: "CCR = \\dfrac{1}{5} \\sum_{t=1}^{5} \\dfrac{FCF_t}{NI_t}",
    what:
      "Average of FCF / Net Income over the last 5 years.",
    why:
      "Confirms that reported profits actually convert to cash. Low CCR signals working-capital build-up or capitalised expenses.",
    goodVsBad:
      "≥1.0 excellent (cash > earnings). 0.8-1.0 healthy. 0.5-0.8 monitor. <0.5 red flag.",
    example:
      "Visa 5y CCR ≈ 1.1. A struggling SaaS with deferred revenue swings may show 0.4.",
    caveats:
      "Returns NaN if fewer than 3 years of valid FCF/NI history. Negative-NI years inflate the ratio artificially.",
  },
  graham_number: {
    label: "Graham Number",
    formula: "\\text{Graham Number} = \\sqrt{22.5 \\cdot EPS \\cdot BVPS}",
    what:
      "Per-share intrinsic value via Benjamin Graham's classic formula: √(22.5 × EPS × BVPS).",
    why:
      "A deep-value sanity check. Graham used it as a maximum acceptable price for defensive investors.",
    goodVsBad:
      "If price < Graham Number, stock is cheap on Graham's terms. Most growth names price above their Graham Number.",
    example:
      "BNP.PA with EPS €8 and BVPS €80 → Graham Number ≈ €120. Stock at €60 → 50% below = deep value.",
    caveats:
      "Misleading for asset-light, high-margin businesses (software). Best for tangible-book industries (banks, industrials).",
  },
  graham_mos: {
    label: "Graham Margin of Safety",
    formula: "\\text{Graham MoS} = \\dfrac{\\text{Graham Number} - \\text{Price}}{\\text{Price}}",
    what:
      "Percentage gap: (Graham Number / Price - 1).",
    why:
      "Quick read on Graham's discount. Serves as a secondary cross-check next to DCF MoS.",
    goodVsBad:
      "≥50% deep Graham value. 0-50% modest discount. <0% Graham fair-or-rich.",
    example:
      "BNP.PA at €60 with Graham €120 → MoS +100%. AAPL at $190 with Graham $40 → MoS -79%.",
    caveats:
      "Graham penalises asset-light businesses harshly; treat as a floor check, not a primary signal.",
  },
  earnings_quality_score: {
    label: "Earnings Quality Score (0-100)",
    formula: "\\text{EQ Score} = \\sum_{m} w_m \\cdot \\text{percentile}_{\\text{sector}}(m), \\quad m \\in \\{\\text{M-Score}, \\text{Sloan}, CCR_{5y}\\}",
    what:
      "Sector-relative composite of M-Score, Sloan accruals, and Cash Conversion Ratio. Higher = cleaner earnings.",
    why:
      "Single number consolidating three accounting-quality signals. Used as a sub-input to the LT and MT composites (10% weight each).",
    goodVsBad:
      "≥70 strong. 50-70 typical. <50 below sector. <30 red flag — combine with M-Score and CCR for context.",
    example:
      "MSFT ≈ 80. A roll-up small-cap with aggressive accruals ≈ 30.",
  },
  moat_score: {
    label: "Moat / Competitive Advantage Score (0-100)",
    formula: "\\text{Moat Score} = \\sum_{m} w_m \\cdot \\text{percentile}_{\\text{sector}}(m), \\quad m \\in \\{GP/TA, \\overline{ROIC}_{5y}, \\sigma(ROIC), \\sigma(OpM), ROIC - WACC\\}",
    what:
      "Sector-relative composite of Gross Profitability (GP/TA), 5y average ROIC, ROIC stability, operating-margin stability, ROIC-WACC spread, and reinvestment efficiency.",
    why:
      "Quantifies durable competitive advantages — what Buffett calls the moat. Stable, high ROIC over many years signals barriers to entry.",
    goodVsBad:
      "≥70 wide moat. 50-70 narrow moat. <40 commodity-like business.",
    example:
      "Hermès Moat Score 85 (consistent ROIC 25-30% for a decade). A specialty distributor ≈ 40.",
  },

  // ============================================================
  // Risk
  // ============================================================
  risk_score: {
    label: "Risk Score (0-100, higher = safer)",
    formula: "\\text{Risk Score} = \\sum_{m} w_m \\cdot (1 - \\text{percentile}_{\\text{sector}}(m)), \\quad m \\in \\{\\text{RealVol}_{1y}, \\text{MaxDD}_{3y}, \\text{ND/EBITDA}, IC, Z'', \\beta_{5y}\\}",
    what:
      "Sector-relative composite of realised volatility (1y), max drawdown (3y), Net Debt / EBITDA, real Interest Coverage, Altman Z'', and 5y monthly Beta.",
    why:
      "One-number safety read combining market and balance-sheet risk. Replaces the v1 anemic 'beta + interest coverage' proxy.",
    goodVsBad:
      "≥70 low risk. 50-70 average. <40 elevated risk. <25 dangerous.",
    example:
      "NVDA Risk Score 88 (clean balance sheet, growth). ATO.PA Risk Score 32 (distress + high vol).",
  },
  realized_vol_1y: {
    label: "Realised Volatility (1Y, annualised)",
    formula: "\\text{RealVol}_{1y} = \\sigma\\left(\\ln \\dfrac{P_t}{P_{t-1}}\\right) \\cdot \\sqrt{252}",
    what:
      "Annualised standard deviation of daily log returns over the past 12 months.",
    why:
      "Realised price-risk measure. Large numbers mean wide swings, sized your stop-loss accordingly.",
    goodVsBad:
      "<20% calm. 20-35% normal equity. 35-60% high. >60% speculative.",
    example:
      "Nestlé ≈ 16%. Tesla 50-70% in volatile years. Atos peaks above 100% during stress periods.",
  },
  max_drawdown_3y: {
    label: "Max Drawdown (3Y)",
    formula: "\\text{MaxDD}_{3y} = \\min_{t} \\dfrac{P_t - \\max_{s \\le t} P_s}{\\max_{s \\le t} P_s}, \\quad t \\in [-756, 0]",
    what:
      "Worst peak-to-trough decline experienced by the stock over the past 36 months. Returned as a negative percentage.",
    why:
      "Captures tail-risk and historical pain. Useful for position sizing and stop placement.",
    goodVsBad:
      "Better than -20% strong. -20% to -40% typical. -40% to -60% painful. <-60% capitulation territory.",
    example:
      "Visa MDD-3y ≈ -25%. ATO.PA MDD-3y often <-80%.",
  },
  net_debt_ebitda: {
    label: "Net Debt / EBITDA",
    formula: "\\dfrac{\\text{Net Debt}}{EBITDA} = \\dfrac{\\text{Total Debt} - \\text{Cash}}{EBITDA}",
    what:
      "(Total Debt - Cash) / EBITDA. How many years of EBITDA it takes to pay off net debt.",
    why:
      "Standard leverage ratio used by credit analysts. Above 4x is the rough investment-grade boundary in most sectors.",
    goodVsBad:
      "<1x conservative. 1-3x normal. 3-4x leveraged. >4x risky. Negative = net cash position (best).",
    example:
      "Apple often runs negative ND/EBITDA (net cash). A typical industrial 1.5-2.5x. Atos 8x+ pre-restructuring.",
    caveats:
      "Banks, REITs, insurers operate differently — leverage ratios are not directly comparable.",
  },
  interest_coverage: {
    label: "Interest Coverage (EBIT / Interest)",
    formula: "\\text{Interest Coverage} = \\dfrac{EBIT}{|\\text{Interest Expense}|}",
    what:
      "EBIT divided by interest expense. How many times current earnings cover the interest bill.",
    why:
      "Solvency ratio. Below 2x means a small earnings dip risks default.",
    goodVsBad:
      "≥10x strong. 4-10x healthy. 2-4x watch. <2x distressed.",
    example:
      "Microsoft 30x+. A leveraged buyout target 2-3x.",
    caveats:
      "M1 fix: this metric now uses real Interest Expense from financial statements, not the v1 fabricated `0.04 × TotalDebt`.",
  },
  beta: {
    label: "Beta (5y monthly vs market)",
    formula: "\\beta = \\dfrac{\\text{Cov}(R_{\\text{stock}},\\, R_{\\text{market}})}{\\text{Var}(R_{\\text{market}})}",
    what:
      "Slope of the stock's monthly returns regressed against the benchmark over 5 years. Measures systematic-risk exposure.",
    why:
      "How much the stock moves relative to the market. Used in CAPM cost-of-equity (Re = Rf + Beta·ERP) inside the DCF.",
    goodVsBad:
      "0.8-1.2 market-like. <0.8 defensive. >1.5 high systematic risk. Negative betas exist (gold miners) but are rare.",
    example:
      "Nestlé ≈ 0.6 (defensive). NVDA ≈ 1.8 (high beta). Utilities ≈ 0.5.",
  },

  // ============================================================
  // Momentum (M9)
  // ============================================================
  momentum_12_1: {
    label: "12-1 Momentum",
    formula: "\\text{Momentum}_{12-1} = \\dfrac{P_{t-21}}{P_{t-252}} - 1",
    what:
      "12-month price return excluding the most recent month: price[t-21] / price[t-252] - 1.",
    why:
      "Academic standard for cross-sectional momentum (Jegadeesh & Titman 1993). Excluding the last month avoids short-term reversal contamination.",
    goodVsBad:
      ">+0.30 strong uptrend. -0.10 to +0.30 mild. <-0.10 downtrend. Top quartile of universe is the screener target for ST_MOMENTUM_QUALITY.",
    example:
      "NVDA 12-1 momentum +1.5 in a strong year. A faded small cap may run -0.45.",
    caveats:
      "Requires ≥252 trading days of price history. Returns NaN otherwise.",
  },
  rs_3m: {
    label: "Relative Strength (3-month vs benchmark)",
    formula: "RS_{3m} = R_{\\text{stock}}(3m) - R_{\\text{benchmark}}(3m), \\quad R(3m) = \\dfrac{P_t}{P_{t-63}} - 1",
    what:
      "3-month return of the stock minus 3-month return of the benchmark index.",
    why:
      "Filters out beta-driven moves. Positive RS_3m = outperforming the index even when the index is choppy.",
    goodVsBad:
      ">+0.05 outperformer. ±0.05 in-line. <-0.05 lagging.",
    example:
      "ASML.AS during a chip rally: +0.18. A fading defensive in a bull market: -0.12.",
  },
  above_50dma: {
    label: "Above 50-Day Moving Average",
    what:
      "Boolean: latest close > rolling 50-day mean of closes.",
    why:
      "Short-term trend filter. ST presets gate on this — momentum trades require the trend to be intact.",
    goodVsBad:
      "True = trend up. False = trend broken on short timeframe.",
    example:
      "A breakout stock hits this true. Stock rolling over after earnings miss flips to false.",
  },
  above_200dma: {
    label: "Above 200-Day Moving Average",
    what:
      "Boolean: latest close > rolling 200-day mean of closes.",
    why:
      "Long-term trend filter. The classic 'bull market vs bear market' line.",
    goodVsBad:
      "True = primary trend up. False = primary trend down.",
    example:
      "ST_OVERSOLD_BOUNCE preset only buys names where above_200dma is True (mean-reversion only in uptrends).",
  },
  golden_cross: {
    label: "Golden Cross (50DMA > 200DMA)",
    what:
      "Boolean: 50-day moving average is above the 200-day moving average.",
    why:
      "Classic technical confirmation that medium-term trend has overtaken long-term trend.",
    goodVsBad:
      "True = bullish confirmation. False = death-cross or sideways.",
    example:
      "After a long base, a stock turns the 50DMA above the 200DMA → golden cross fires.",
  },
  volume_surge: {
    label: "Volume Surge (5d / 90d)",
    formula: "\\text{Volume Surge} = \\dfrac{\\overline{V}_{5d}}{\\overline{V}_{90d}}",
    what:
      "5-day average volume divided by 90-day average volume.",
    why:
      "Conviction check. Breakouts on heavy volume are stronger than quiet breakouts.",
    goodVsBad:
      ">1.3 surge. 0.8-1.3 normal. <0.8 fading interest.",
    example:
      "A 2.0 reading after earnings indicates institutional buying. 0.5 = market losing interest.",
  },
  eps_revision_30d: {
    label: "EPS Revision (30 days)",
    formula: "\\text{EPS Rev}_{30d} = \\dfrac{EPS^{\\text{est}}_t}{EPS^{\\text{est}}_{t-30d}} - 1",
    what:
      "% change in median consensus EPS estimate over the past 30 days.",
    why:
      "Captures analyst behaviour right after company guidance updates. Strongest predictor inside MT_GARP and MT_TURNAROUND presets.",
    goodVsBad:
      ">+2% positive revisions. ±2% flat. <-2% negative revisions.",
    example:
      "A guidance raise can lift EPS_Rev_30d to +5%; a miss can crash it to -8%.",
  },
  eps_revision_90d: {
    label: "EPS Revision (90 days)",
    formula: "\\text{EPS Rev}_{90d} = \\dfrac{EPS^{\\text{est}}_t}{EPS^{\\text{est}}_{t-90d}} - 1",
    what:
      "% change in median consensus EPS estimate over the past 90 days.",
    why:
      "Smoother trend than the 30-day reading. Filters out single-event spikes.",
    goodVsBad:
      ">+5% sustained upgrades. ±5% normal noise. <-5% sustained downgrades.",
    example:
      "Cyclical stock during expansion: +8%. Falling-knife industrial: -12%.",
  },
  sue_z_score: {
    label: "SUE (Standardized Unexpected Earnings)",
    formula: "SUE = \\dfrac{EPS_{\\text{actual}} - EPS_{\\text{expected}}}{\\sigma(\\text{prior 4 quarters})}",
    what:
      "(Reported EPS - Expected EPS) / stddev of prior 4 quarters' surprises. How many standard deviations a beat or miss is.",
    why:
      "Drives Post-Earnings Announcement Drift (PEAD). Strong beats persist for 1-3 months on average.",
    goodVsBad:
      ">+1.5 strong beat. ±1.0 in-line. <-1.5 strong miss.",
    example:
      "NVDA beats by 20% on consensus → SUE z ≈ +2.5. A struggling retailer missing by 15% → SUE z ≈ -1.8.",
  },
  sentiment_30d: {
    label: "News Sentiment (30 days)",
    formula: "\\text{Sentiment}_{30d} = \\dfrac{\\#\\,\\text{positive}}{\\#\\,\\text{total}} \\cdot 100",
    what:
      "FinBERT-classified positive/negative news ratio over the past 30 days, mapped to 0-100.",
    why:
      "Cross-checks momentum signals with narrative direction. Useful filter against pure technical signals.",
    goodVsBad:
      "≥70 positive. 30-70 neutral. <30 negative.",
    example:
      "A name with consistent product launches scores 75. A company in regulatory trouble scores 20.",
    caveats:
      "Optional dependency on transformers; returns NaN if FinBERT not loaded. ST gates allow NaN to pass with neutral default.",
  },
  sentiment_trend: {
    label: "Sentiment Trend",
    what:
      "Slope of 7-day rolling positivity over the 30-day window. Positive = improving narrative, negative = deteriorating.",
    why:
      "Captures inflection points faster than the absolute level.",
    goodVsBad:
      ">0 improving. <0 deteriorating. Magnitude indicates speed of change.",
    example:
      "Sentiment improving from 30 to 55 over 4 weeks → strong positive trend.",
  },

  // ============================================================
  // Valuation ratios
  // ============================================================
  pe: {
    label: "P/E Ratio (Price / Earnings)",
    formula: "P/E = \\dfrac{\\text{Price}}{EPS_{TTM}}",
    what:
      "Stock price divided by trailing 12-month earnings per share.",
    why:
      "Most-cited valuation metric. Compares price paid per €1 of profit. The screener's sector-relative ranking penalises richness within peers.",
    goodVsBad:
      "Sector-dependent. Tech 20-40 normal. Utilities 10-15 normal. <8 in healthy stock = potential value. Negative P/E = unprofitable (penalised in valuation score).",
    example:
      "Nestlé ≈ 22. NVDA at growth peak ≈ 60. A struggling retailer ≈ -15 (no earnings).",
    caveats:
      "Distorted by one-off gains/losses. Use forward_pe for forward-looking comparisons.",
  },
  forward_pe: {
    label: "Forward P/E (next-year estimate)",
    formula: "\\text{Fwd P/E} = \\dfrac{\\text{Price}}{EPS^{\\text{est}}_{NTM}}",
    what:
      "Price divided by consensus EPS estimate for the next fiscal year.",
    why:
      "Captures analyst-expected growth; cleaner for cyclicals coming out of a trough.",
    goodVsBad:
      "Same logic as P/E but typically lower (assumes earnings growth). Forward P/E above trailing P/E = analysts expect lower earnings (warning).",
    example:
      "ASML.AS trailing 30, forward 22 → strong earnings growth expected.",
  },
  pb: {
    label: "P/B Ratio (Price / Book)",
    formula: "P/B = \\dfrac{\\text{Market Cap}}{\\text{Book Value of Equity}}",
    what:
      "Market cap divided by shareholders' book equity.",
    why:
      "Tangible-asset valuation. Critical for banks, insurers, asset-heavy industries. Less informative for software / IP-heavy businesses.",
    goodVsBad:
      "Banks 0.6-1.5 normal. Industrials 1-3. Software 5-15. <1 may signal distress OR deep value (check Altman).",
    example:
      "BNP.PA ≈ 0.6 (typical for European banks). Apple ≈ 50 (very asset-light).",
  },
  ps: {
    label: "P/S Ratio (Price / Sales)",
    formula: "P/S = \\dfrac{\\text{Market Cap}}{\\text{Revenue}_{TTM}}",
    what:
      "Market cap divided by trailing-12-month revenue.",
    why:
      "Useful when earnings are negative or volatile (early growth, cyclicals). Less manipulable than earnings.",
    goodVsBad:
      "<1 cheap (sometimes too cheap to be true). 1-3 typical. 3-10 premium. >10 high-growth premium territory.",
    example:
      "Walmart ≈ 0.7. NVIDIA at peak ≈ 35.",
    caveats:
      "Ignores margin structure — a 10% margin business and a 2% margin business can have the same P/S.",
  },
  pfcf: {
    label: "P/FCF Ratio (Price / Free Cash Flow)",
    formula: "P/FCF = \\dfrac{\\text{Market Cap}}{FCF_{TTM}}, \\quad FCF = CFO - CapEx",
    what:
      "Market cap divided by trailing-12-month free cash flow.",
    why:
      "Cash-based valuation. Harder to manipulate than P/E. Aligns with what shareholders can actually receive.",
    goodVsBad:
      "<10 cheap. 10-25 normal. 25-40 premium. >40 expensive (or negative FCF). Negative FCF = ratio meaningless, score skipped.",
    example:
      "Microsoft ≈ 30. A real-estate developer in a downcycle may show negative FCF (excluded).",
  },
  ev_ebitda: {
    label: "EV / EBITDA",
    formula: "\\dfrac{EV}{EBITDA} = \\dfrac{\\text{Market Cap} + \\text{Debt} - \\text{Cash}}{EBITDA}",
    what:
      "Enterprise Value (market cap + debt - cash) divided by EBITDA.",
    why:
      "Capital-structure-neutral valuation. Comparable across leveraged and unleveraged peers.",
    goodVsBad:
      "<8 cheap. 8-15 normal. 15-25 premium. >25 expensive.",
    example:
      "A typical European industrial 8-12. Premium tech name 18-25.",
  },
  ev_sales: {
    label: "EV / Sales",
    formula: "\\dfrac{EV}{\\text{Sales}} = \\dfrac{EV}{\\text{Revenue}_{TTM}}",
    what:
      "Enterprise Value divided by trailing revenue.",
    why:
      "Revenue-based version of EV/EBITDA. Useful for unprofitable growth companies.",
    goodVsBad:
      "<2 cheap. 2-5 normal. >8 high growth premium.",
    example:
      "SaaS leader at 12 (priced for growth). Mature retailer at 0.3.",
  },
  peg: {
    label: "PEG Ratio",
    formula: "PEG = \\dfrac{P/E}{g_{EPS}\\,(\\%)}",
    what:
      "P/E divided by expected EPS growth rate.",
    why:
      "Adjusts P/E for growth — bridges value and growth philosophies.",
    goodVsBad:
      "<1 attractive (growth not priced in). 1-2 fair. >2 expensive even for growth.",
    example:
      "GARP target: PEG 0.8-1.3. A hyper-growth name with PEG 0.6 is rare and worth investigating.",
    caveats:
      "Growth estimates are forward-looking and uncertain. Manipulable.",
  },

  // ============================================================
  // Profitability
  // ============================================================
  roe: {
    label: "ROE (Return on Equity)",
    formula: "ROE = \\dfrac{\\text{Net Income}}{\\text{Shareholders' Equity}}",
    what:
      "Net Income divided by shareholders' equity. How efficiently the company turns equity into profit.",
    why:
      "Core profitability metric. High and stable ROE is a moat indicator.",
    goodVsBad:
      ">20% excellent. 12-20% strong. 6-12% average. <6% weak. Negative = unprofitable.",
    example:
      "MasterCard 100%+ (highly leveraged). Nestlé 20-30%. Cyclical industrial 8-15%.",
    caveats:
      "Leverage inflates ROE; combine with ROIC for unleveraged read.",
  },
  roa: {
    label: "ROA (Return on Assets)",
    formula: "ROA = \\dfrac{\\text{Net Income}}{\\text{Total Assets}}",
    what:
      "Net Income divided by total assets. Asset-efficiency measure.",
    why:
      "Cleaner than ROE because it ignores capital structure.",
    goodVsBad:
      ">10% excellent. 5-10% strong. 2-5% average. <2% weak.",
    example:
      "Software 15-25%. Bank 0.5-1.5% (different scale due to balance-sheet size).",
    caveats:
      "Banks and insurers run very low ROAs by design — compare within sector.",
  },
  roic: {
    label: "ROIC (Return on Invested Capital)",
    formula: "ROIC = \\dfrac{NOPAT}{\\text{Invested Capital}}, \\quad NOPAT = EBIT \\cdot (1 - t)",
    what:
      "NOPAT (EBIT after tax) divided by invested capital (equity + debt - cash).",
    why:
      "The 'true' profitability metric — leverage-neutral and cash-adjusted. ROIC > WACC means the business creates value.",
    goodVsBad:
      ">20% wide-moat. 12-20% strong. WACC threshold ≈ 8-10%; below that destroys value.",
    example:
      "Hermès 25-30%. A capital-heavy mid-cap 8-10%. Steel mill 4-7% (often below WACC).",
  },
  gross_margin: {
    label: "Gross Margin",
    formula: "\\text{Gross Margin} = \\dfrac{\\text{Revenue} - COGS}{\\text{Revenue}}",
    what:
      "(Revenue - COGS) / Revenue. Profit per €1 of revenue before operating expenses.",
    why:
      "Reflects pricing power. High and rising gross margins are a moat indicator.",
    goodVsBad:
      "Sector-dependent. Software 70-90%. Luxury 60-70%. Retail 25-35%. Commodity producers 10-20%.",
    example:
      "Visa ≈ 80%. Walmart ≈ 25%. A discount retailer ≈ 20%.",
  },
  operating_margin: {
    label: "Operating Margin",
    formula: "\\text{Operating Margin} = \\dfrac{\\text{Operating Income}}{\\text{Revenue}}",
    what:
      "Operating Income / Revenue. Margin after operating expenses but before interest and taxes.",
    why:
      "Captures operational efficiency. Trend is more important than the absolute level.",
    goodVsBad:
      ">20% strong. 10-20% normal. <5% thin. Negative = operating losses.",
    example:
      "Microsoft 40%. Auto OEM 6-10%. Airline 0-12% (volatile).",
  },
  net_margin: {
    label: "Net Margin",
    formula: "\\text{Net Margin} = \\dfrac{\\text{Net Income}}{\\text{Revenue}}",
    what:
      "Net Income / Revenue. Bottom-line profitability.",
    why:
      "Net of interest, taxes and one-offs. Compares apples to apples across capital structures.",
    goodVsBad:
      ">15% strong. 5-15% typical. <2% thin. Negative = unprofitable.",
    example:
      "Apple 25%. Walmart 2-3%. Bank net margin not directly comparable.",
  },
  fcf_margin: {
    label: "FCF Margin",
    formula: "\\text{FCF Margin} = \\dfrac{FCF}{\\text{Revenue}}",
    what:
      "Free Cash Flow / Revenue. Cash earned per €1 of revenue.",
    why:
      "Cash-quality companion to net margin. Gap between net margin and FCF margin signals capex intensity or working-capital build.",
    goodVsBad:
      ">15% excellent. 8-15% healthy. <5% capital-intensive. Negative = cash-burning growth.",
    example:
      "Software 25-35%. A capital-heavy industrial 5-8%. Pre-revenue biotech negative.",
  },

  // ============================================================
  // Health
  // ============================================================
  current_ratio: {
    label: "Current Ratio",
    formula: "\\text{Current Ratio} = \\dfrac{\\text{Current Assets}}{\\text{Current Liabilities}}",
    what:
      "Current Assets / Current Liabilities. Short-term liquidity check.",
    why:
      "Captures whether the company can meet 12-month obligations from current assets.",
    goodVsBad:
      ">1.5 healthy. 1.0-1.5 adequate. <1.0 short-term stress.",
    example:
      "A typical industrial 1.5-2.5. Retailer 1.0-1.4 (fast inventory turn).",
    caveats:
      "Banks operate on different ratios entirely (liquidity coverage ratio).",
  },
  debt_equity: {
    label: "Debt / Equity Ratio",
    formula: "D/E = \\dfrac{\\text{Total Debt}}{\\text{Shareholders' Equity}}",
    what:
      "Total Debt divided by shareholders' equity.",
    why:
      "Capital structure read. High D/E = more financial risk and higher interest burden.",
    goodVsBad:
      "<0.5 conservative. 0.5-1.5 normal. >2.0 leveraged. Negative equity = severe distress.",
    example:
      "Nestlé ≈ 0.6. A leveraged buyout target 4.0+. Apple net cash → effective D/E negative.",
  },
  revenue_growth: {
    label: "Revenue Growth (YoY)",
    formula: "\\text{Revenue Growth} = \\dfrac{\\text{Revenue}_{TTM}}{\\text{Revenue}_{TTM,\\,t-1y}} - 1",
    what:
      "Year-over-year change in trailing-12-month revenue.",
    why:
      "Top-line growth signal. The screener's growth sub-score uses this directly; multi-period CAGR is on the M14 roadmap.",
    goodVsBad:
      ">10% strong. 3-10% normal. 0-3% slow. <0 contracting (red flag unless cyclical trough).",
    example:
      "Hyper-growth tech 30%+. Mature consumer staple 3-5%. A struggling retailer -8%.",
    caveats:
      "Single-period reading is noisy. Multi-year consistency matters more — combine with Piotroski signal #2.",
  },

  // ============================================================
  // Dividend
  // ============================================================
  div_yield: {
    label: "Dividend Yield",
    formula: "\\text{Dividend Yield} = \\dfrac{\\text{Annual DPS}}{\\text{Price}}",
    what:
      "Annual dividend per share divided by stock price.",
    why:
      "Income-investor focal metric. PEA wrapper turns this into a tax-efficient compounding vehicle after 5 years.",
    goodVsBad:
      "0-2% growth-focused. 2-4% balanced. 4-6% income. >6% potential dividend trap (check payout ratio).",
    example:
      "Total Energies 5%. Apple 0.5%. A leveraged REIT 8%+ with risk.",
    caveats:
      "Yield can spike because price collapsed. Always check sustainability via payout_ratio and FCF coverage.",
  },
  payout_ratio: {
    label: "Payout Ratio",
    formula: "\\text{Payout Ratio} = \\dfrac{\\text{Dividends Paid}}{\\text{Net Income}}",
    what:
      "Dividends paid divided by net income (or by FCF, depending on convention).",
    why:
      "Sustainability check. A 90% payout ratio leaves no room for reinvestment or downturns.",
    goodVsBad:
      "30-60% balanced. <30% conservative (reinvesting). 60-80% mature high payout. >80% caution. >100% unsustainable.",
    example:
      "Apple ≈ 15%. Nestlé 70%. A REIT structurally 90%+ (different rules).",
  },

  // ============================================================
  // Sub-scores (legacy M3)
  // ============================================================
  sub_valuation: {
    label: "Valuation Sub-Score (0-100)",
    formula: "\\text{sub\\_val} = \\overline{\\text{percentile}_{\\text{sector}}(m)}, \\quad m \\in \\{P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/S\\}",
    what:
      "Sector-relative percentile rank across 6 valuation ratios: P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/Sales. Lower ratios → higher score.",
    why:
      "A single number summarising 'how cheap vs peers'. Feeds the LT/MT/ST composites with horizon-specific weights.",
    goodVsBad:
      "≥75 cheaper than peers on most metrics. 40-60 in line. <30 expensive vs peers.",
    example:
      "BNP.PA in European banks ≈ 80 (cheap). NVDA ≈ 25 (expensive within tech).",
  },
  sub_profitability: {
    label: "Profitability Sub-Score (0-100)",
    formula: "\\text{sub\\_prof} = \\overline{\\text{percentile}_{\\text{sector}}(m)}, \\quad m \\in \\{ROE, ROA, ROIC, GM, OM, NM, FCFM\\}",
    what:
      "Sector-relative composite of ROE, ROA, ROIC, gross/operating/net/FCF margins.",
    why:
      "Quality summary on profitability dimension only. 25% weight in LT composite.",
    goodVsBad:
      "≥75 top-quartile profitable. 40-60 average. <30 below sector.",
    example:
      "Hermès 95+. Cyclical commodity producer 30-45.",
  },
  sub_health: {
    label: "Financial Health Sub-Score (0-100)",
    formula: "\\text{sub\\_health} = \\overline{\\text{percentile}_{\\text{sector}}(m)}, \\quad m \\in \\{CR, D/E, IC, ND/EBITDA\\}",
    what:
      "Sector-relative composite of Current Ratio, D/E, Interest Coverage, Net Debt / EBITDA.",
    why:
      "Balance-sheet strength summary. 15-20% weight in horizon composites.",
    goodVsBad:
      "≥70 strong balance sheet. 40-70 normal. <40 leveraged or fragile.",
    example:
      "Apple ≈ 90 (net cash). A leveraged industrial ≈ 35.",
  },
  sub_growth: {
    label: "Growth Sub-Score (0-100)",
    formula: "\\text{sub\\_growth} = \\text{percentile}_{\\text{sector}}(\\text{Revenue Growth}_{YoY})",
    what:
      "Sector-relative ranking of revenue growth (YoY). Limited to one metric in v2; multi-period CAGR is a roadmap item.",
    why:
      "Top-line trajectory captured in a single number. 10-15% weight in horizon composites.",
    goodVsBad:
      "≥75 high-growth in sector. 40-60 typical. <30 stalling or contracting.",
    example:
      "ASML.AS during chip cycle peak ≈ 80. A mature staple ≈ 40.",
  },
  sub_shareholder: {
    label: "Shareholder Returns Sub-Score (0-100)",
    formula: "\\text{sub\\_shareholder} = \\overline{\\text{percentile}_{\\text{sector}}(m)}, \\quad m \\in \\{\\text{Div Yield}, \\text{Payout sust.}\\}",
    what:
      "Sector-relative read on dividend yield + payout-ratio sustainability. Buybacks are tracked separately and not yet folded in.",
    why:
      "Captures the 'cash to shareholders' dimension. 5-10% weight in horizon composites.",
    goodVsBad:
      "≥70 strong sustainable yield. 40-60 normal. <30 either no yield or unsustainable payout.",
    example:
      "Total Energies ≈ 80. A non-dividend tech name ≈ 35.",
    caveats:
      "M5 roadmap: extend with Total Shareholder Yield (div + buyback + debt reduction).",
  },
  sub_risk_legacy: {
    label: "Risk Sub-Score (legacy, 0-100)",
    what:
      "Original v1 risk read using only Beta and Interest Coverage. Kept for schema stability; superseded by Risk Score v2.",
    why:
      "Backwards compatibility. New code should consume `risk_score` (v2) which adds vol, max DD, ND/EBITDA, real Altman Z''.",
    goodVsBad:
      "Same scale as risk_score: higher = safer. But the v1 metric is less informative; trust risk_score over this.",
    example:
      "v1 may read 50 on a name where v2 reads 30 (because v2 sees the high vol).",
    caveats:
      "Will be removed in a future schema cleanup once frontend fully consumes Risk Score v2.",
  },

  // ============================================================
  // Portfolio summary
  // ============================================================
  total_value: {
    label: "Total Portfolio Value",
    formula: "\\text{Total Value} = \\sum_{i \\in \\text{positions}} Q_i \\cdot P_i",
    what:
      "Sum of market values across all positions, in EUR (or your reporting currency).",
    why:
      "Top-line portfolio number. Drives weight calculations and overall performance tracking.",
    goodVsBad:
      "Up = portfolio appreciated and/or you added cash. Down = depreciation and/or withdrawals.",
    example:
      "10 positions × €5k = €50k portfolio.",
  },
  total_gain_loss: {
    label: "Total Gain / Loss",
    formula: "\\text{Total Gain/Loss} = \\sum_{i \\in \\text{positions}} (MV_i - CB_i)",
    what:
      "Current total value minus total cost basis. Cumulative P&L since inception of each position.",
    why:
      "Realised + unrealised P&L combined. The simplest 'am I winning' read.",
    goodVsBad:
      "Positive = profitable. Negative = drawdown. Compare against benchmark (CAC40 for PEA, MSCI World for global) for context.",
    example:
      "€50k portfolio with €43k cost basis → +€7k or +16% gain.",
  },
  avg_score_lt: {
    label: "Average LT Score",
    formula: "\\overline{\\text{score}_{LT}} = \\dfrac{1}{N} \\sum_{i=1}^{N} \\text{score}_{LT,i}",
    what:
      "Mean of the long-term composite scores across all current positions.",
    why:
      "Quality temperature of the whole book. Drift below 60 suggests rebalancing toward higher-quality names.",
    goodVsBad:
      "≥70 high-quality book. 55-70 mixed. <50 low-quality or speculative book.",
    example:
      "A buy-and-hold quality portfolio averages 75+. A momentum-trading book averages 50-60.",
  },
  weight_pct: {
    label: "Position Weight",
    formula: "w_i = \\dfrac{MV_i}{\\sum_{j} MV_j}",
    what:
      "Position market value divided by total portfolio value.",
    why:
      "Concentration check. Position-sizing rules in settings.yaml cap individual weights at 10%.",
    goodVsBad:
      "<5% small. 5-10% normal core position. >10% concentrated bet (intentional or drift?).",
    example:
      "A 12% weight on one stock means it drives more than its share of P&L — consider trimming.",
  },
  position_count: {
    label: "Position Count",
    what:
      "Number of distinct holdings in the portfolio.",
    why:
      "Diversification gauge. The settings.yaml minimum is 15 positions for a properly diversified PEA.",
    goodVsBad:
      "≥15 well diversified. 8-15 concentrated. <8 high single-name risk.",
    example:
      "A typical PEA Quality book runs 18-25 positions.",
  },

  // ============================================================
  // Screener summary
  // ============================================================
  total_passed: {
    label: "Stocks Passed",
    what:
      "Number of tickers that survived every filter for the active preset / horizon.",
    why:
      "Read of the preset's strictness vs your data quality. A consistently empty count usually means a gate (data_completeness, distress) is too strict for your universe.",
    goodVsBad:
      "5-30 tractable for review. 0 = preset too strict OR universe missing required columns. 100+ = filters too loose.",
    example:
      "LT_QUALITY_COMPOUNDER on a clean PEA universe: 8-15 names. ST_MOMENTUM: 3-7 on a small universe.",
  },
  signal_distribution: {
    label: "Signal Distribution",
    what:
      "Counts of Strong Buy / Buy / Hold / Sell / Strong Sell across the screened or held universe.",
    why:
      "Quick read on aggregate market sentiment as judged by your scoring engine.",
    goodVsBad:
      "More Buys than Sells = bullish skew. Equal split = neutral. Heavy Sell skew = late-cycle or your filters too quality-focused.",
    example:
      "{Strong Buy: 1, Buy: 4, Hold: 12, Sell: 6, Strong Sell: 2} on a 25-ticker universe.",
  },

  // ============================================================
  // Position-level extras
  // ============================================================
  market_value: {
    label: "Market Value",
    formula: "MV = Q \\cdot P_{\\text{current}}",
    what:
      "Quantity × current price. Today's mark-to-market value of this position.",
    why:
      "Current worth — what you would receive selling at last close.",
    goodVsBad:
      "Higher than cost basis = unrealised gain. Lower = unrealised loss.",
    example:
      "100 shares × €50 = €5,000 market value.",
  },
  cost_basis: {
    label: "Cost Basis",
    formula: "CB = Q \\cdot \\overline{P}_{\\text{buy}}",
    what:
      "Quantity × buy price. Total amount you paid to acquire this position.",
    why:
      "Anchors the gain/loss calculation. Stays constant unless you add to the position.",
    goodVsBad:
      "Used as denominator for return %. No good/bad in isolation.",
    example:
      "100 shares × €43 = €4,300 cost basis.",
  },
  gain_loss_pct: {
    label: "Gain / Loss %",
    formula: "\\text{Gain/Loss \\%} = \\dfrac{MV - CB}{CB}",
    what:
      "(Market value - cost basis) / cost basis. Total return on this position since purchase.",
    why:
      "Return measure for individual positions.",
    goodVsBad:
      "Positive = profit. Negative = loss. Compare against benchmark return over the same holding period.",
    example:
      "Bought at €43, now €50 → +16.3%.",
    caveats:
      "Excludes dividends received and taxes/fees.",
  },
  fifty_two_week_high_pct: {
    label: "52-Week High (% off)",
    formula: "\\text{52w High \\%} = \\dfrac{P_{\\text{current}} - P_{52wH}}{P_{52wH}}",
    what:
      "(Current price - 52w high) / 52w high. How far below this year's peak the stock trades.",
    why:
      "Momentum + drawdown context. Trades far off highs may be value opportunities or value traps.",
    goodVsBad:
      "0% to -10% near highs (momentum). -10% to -25% pullback territory. <-25% deep drawdown.",
    example:
      "A leader at -3% off highs is in a strong trend. A struggling cyclical at -45% is in correction.",
  },
  pea_eligible: {
    label: "PEA Eligible",
    what:
      "Boolean: is this stock eligible to be held inside a French PEA wrapper?",
    why:
      "Eligibility requires HQ in EU/EEA. Determines whether the tax advantages apply.",
    goodVsBad:
      "True = can be held in PEA. False = must be held in CTO.",
    example:
      "Hermès, ASML, SAP all True. Apple, Nestlé False (Nestlé is Swiss — outside EEA).",
  },

  // ============================================================
  // Analyst
  // ============================================================
  analyst_rating: {
    label: "Analyst Consensus",
    what:
      "Aggregated sell-side analyst opinion (Strong Buy / Buy / Hold / Sell / Strong Sell).",
    why:
      "External cross-check on your scoring. Useful as a sanity gauge but rarely a leading indicator.",
    goodVsBad:
      "Strong Buy / Buy = bullish consensus. Hold = neutral. Sell signals usually lag the price drop.",
    example:
      "5 Strong Buy, 18 Buy, 4 Hold = strong bullish consensus.",
    caveats:
      "Sell-side ratings are notoriously slow to downgrade and biased toward Buy.",
  },
  analyst_target_price: {
    label: "Analyst Target Price",
    what:
      "Mean (or median) 12-month forward price target from sell-side analysts.",
    why:
      "Market expectation of where the stock is heading. Gap vs current price = implied analyst MoS.",
    goodVsBad:
      "Above current price = upside expected. Below = downside expected. Compare against your DCF MoS.",
    example:
      "Stock at €100, target €120 → analysts see +20% upside.",
  },
};
