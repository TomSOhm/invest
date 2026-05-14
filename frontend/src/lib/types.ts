// ---------------------------------------------------------------------------
// Horizon type
// ---------------------------------------------------------------------------

export type Horizon = "long_term" | "medium_term" | "short_term";

export type Signal = "Strong Buy" | "Buy" | "Hold" | "Sell" | "Strong Sell" | "Insufficient Data";

// ---------------------------------------------------------------------------
// Data source (which backend the user wants to feed live fetches)
// ---------------------------------------------------------------------------

export type DataSource = "hybrid" | "yfinance" | "fmp";

export const DATA_SOURCES: DataSource[] = ["hybrid", "yfinance", "fmp"];

// ---------------------------------------------------------------------------
// Chart types (price history endpoint)
// ---------------------------------------------------------------------------

export type ChartPeriod = "1M" | "3M" | "6M" | "1Y" | "5Y" | "MAX";

export const CHART_PERIODS: ChartPeriod[] = ["1M", "3M", "6M", "1Y", "5Y", "MAX"];

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartMetrics {
  total_return: number | null;
  cagr: number | null;
  annualized_vol: number | null;
  max_drawdown: number | null;
  beta: number | null;
  sharpe: number | null;
}

export interface MovingAverages {
  ma_50: (number | null)[];
  ma_200: (number | null)[];
}

export interface PriceHistoryResponse {
  ticker: string;
  period: ChartPeriod;
  benchmark: string | null;
  candles: Candle[];
  benchmark_candles: Candle[];
  metrics: ChartMetrics;
  moving_averages: MovingAverages;
}

// ---------------------------------------------------------------------------
// Horizon scoring block (mirrors backend HorizonScoring)
// ---------------------------------------------------------------------------

export interface HorizonScoring {
  score: number;
  signal: Signal;
  passes_gates: boolean;
  blockers: string[];
  recommended_account?: "PEA" | "CTO" | null;
}

// ---------------------------------------------------------------------------
// DCF valuation block (mirrors backend DCFValuation)
// ---------------------------------------------------------------------------

export interface DCFValuation {
  fair_value_low?: number | null;
  fair_value_mid?: number | null;
  fair_value_high?: number | null;
  mos_low?: number | null;
  mos_mid?: number | null;
  mos_high?: number | null;
  wacc_used?: number | null;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Quality signals block (mirrors backend QualitySignals)
// ---------------------------------------------------------------------------

export interface QualitySignals {
  piotroski_f?: number | null;
  piotroski_satisfied?: number | null;
  piotroski_violated?: number | null;
  piotroski_unknown?: number | null;
  altman_z?: number | null;
  altman_zone?: "Safe" | "Grey" | "Distress" | null;
  graham_number?: number | null;
  graham_mos?: number | null;
  earnings_quality_score?: number | null;
  moat_score?: number | null;
  m_score?: number | null;
  sloan_accruals?: number | null;
  cash_conversion_ratio_5y?: number | null;
}

// ---------------------------------------------------------------------------
// Risk signals block (mirrors backend RiskSignals)
// ---------------------------------------------------------------------------

export interface RiskSignals {
  risk_score?: number | null;
  realized_vol_1y?: number | null;
  max_drawdown_3y?: number | null;
  net_debt_ebitda?: number | null;
  interest_coverage?: number | null;
  beta?: number | null;
}

// ---------------------------------------------------------------------------
// Momentum signals block (mirrors backend MomentumSignals)
// ---------------------------------------------------------------------------

export interface MomentumSignals {
  momentum_12_1?: number | null;
  rs_3m?: number | null;
  above_50dma?: boolean | null;
  above_200dma?: boolean | null;
  golden_cross?: boolean | null;
  volume_surge?: number | null;
  eps_revision_30d?: number | null;
  eps_revision_90d?: number | null;
  sue_z_score?: number | null;
  sentiment_30d?: number | null;
  sentiment_trend?: number | null;
  eps_estimate_trend?: EpsEstimateTrendRow[] | null;
}

// ---------------------------------------------------------------------------
// Sub-scores block (mirrors backend SubScores)
// ---------------------------------------------------------------------------

export interface SubScores {
  valuation: number;
  health: number;
  profitability: number;
  growth: number;
  shareholder: number;
  risk_legacy: number;
}

// ---------------------------------------------------------------------------
// Analyst ratings
// ---------------------------------------------------------------------------

export interface AnalystChange {
  date: string;
  firm: string;
  from_grade: string;
  to_grade: string;
  action: string;
}

export interface EpsRevisionRow {
  period: string; // "7d" | "30d" | "60d" | "90d"
  up: number;
  down: number;
}

export interface EarningsHistoryRow {
  date: string;
  eps_actual: number | null;
  eps_estimate: number | null;
  eps_difference?: number | null;
  surprise_pct: number | null;
}

export interface EpsEstimateTrendRow {
  period: string;
  current: number | null;
  n_minus_7d: number | null;
  n_minus_30d: number | null;
  n_minus_60d: number | null;
  n_minus_90d: number | null;
}

// Sub-project 3 (yfinance.calendars enrichment)
export interface DividendInfo {
  ex_date: string;
  amount: number;
}

export interface CompanyCalendar {
  next_earnings_date: string | null;
  next_earnings_eps_estimate: number | null;
  next_earnings_eps_low: number | null;
  next_earnings_eps_high: number | null;
  next_earnings_revenue_estimate: number | null;
  dividend_date: string | null;
  ex_dividend_date: string | null;
  dividend_amount: number | null;
  dividend_yield: number | null;
  dividend_rate: number | null;
  dividends_5y: DividendInfo[];
}

export interface AnalystRatings {
  buy: number;
  hold: number;
  sell: number;
  strong_buy: number;
  strong_sell: number;
  target_low: number | null;
  target_mean: number | null;
  target_high: number | null;
  target_median: number | null;
  // Sub-project 2 — yfinance.analysis enrichment (all optional)
  num_analysts?: number | null;
  recent_changes?: AnalystChange[] | null;
  revisions_history?: EpsRevisionRow[] | null;
  growth_estimate_fy?: number | null;
  growth_estimate_5y?: number | null;
  earnings_history?: EarningsHistoryRow[] | null;
}

// ---------------------------------------------------------------------------
// Raw financial metrics
// ---------------------------------------------------------------------------

export interface CompanyMetrics {
  ticker: string;
  name: string;
  sector?: string | null;
  industry?: string | null;
  country?: string | null;
  exchange?: string | null;
  price?: number | null;
  market_cap?: number | null;
  enterprise_value?: number | null;
  pe?: number | null;
  forward_pe?: number | null;
  pb?: number | null;
  ps?: number | null;
  pfcf?: number | null;
  ev_ebitda?: number | null;
  ev_sales?: number | null;
  peg?: number | null;
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  fcf_margin?: number | null;
  roe?: number | null;
  roa?: number | null;
  roic?: number | null;
  revenue_growth?: number | null;
  current_ratio?: number | null;
  debt_equity?: number | null;
  interest_coverage?: number | null;
  div_yield?: number | null;
  payout_ratio?: number | null;
  beta?: number | null;
  fifty_two_week_high?: number | null;
  fifty_two_week_low?: number | null;
  fifty_two_week_high_pct?: number | null;
  insider_pct?: number | null;
  institutional_pct?: number | null;
  short_pct_float?: number | null;
  earnings_surprise_pct?: number | null;
}

// ---------------------------------------------------------------------------
// Full company detail (M10 schema — no legacy composite_score/ScoringBreakdown)
// ---------------------------------------------------------------------------

export interface CompanyDetail {
  ticker: string;
  name: string;
  sector?: string | null;
  industry?: string | null;
  country?: string | null;
  exchange?: string | null;
  pea_eligible: boolean;
  pea_pme_eligible: boolean;
  price?: number | null;
  market_cap?: number | null;
  horizons: Record<Horizon, HorizonScoring>;
  sub_scores: SubScores;
  valuation: DCFValuation;
  quality: QualitySignals;
  risk: RiskSignals;
  momentum: MomentumSignals;
  metrics: CompanyMetrics;
  analyst_ratings?: AnalystRatings | null;
  data_completeness: number;
  data_source: DataSource;
  effective_source: DataSource;
  source_fallback_message?: string | null;
  last_updated: string;
  score_source: "universe" | "single_row_fallback";
}

// ---------------------------------------------------------------------------
// Screener
// ---------------------------------------------------------------------------

export interface ScreenerRequest {
  horizon: Horizon;
  preset?: string | null;
  custom_filters?: Record<string, unknown> | null;
  pea_only: boolean;
  sort_by: string;
  sort_desc: boolean;
  limit: number;
}

export interface ScreenerResultItem {
  ticker: string;
  name?: string | null;
  sector?: string | null;
  pea_eligible: boolean;
  score_lt: number;
  score_mt: number;
  score_st: number;
  signal_lt: string;
  signal_mt: string;
  signal_st: string;
  passes_gates_lt: boolean;
  passes_gates_mt: boolean;
  passes_gates_st: boolean;
  pe?: number | null;
  pb?: number | null;
  roe?: number | null;
  div_yield?: number | null;
  revenue_growth?: number | null;
  market_cap?: number | null;
  altman_z?: number | null;
  piotroski_f?: number | null;
  dcf_mos_mid?: number | null;
  recommended_account?: string | null;
  blockers: string[];
}

export interface ScreenerSummary {
  total_passed: number;
  total_universe: number;
  avg_score?: number | null;
  signal_distribution: Record<string, number>;
  horizon: string;
}

export interface ScreenerResponse {
  results: ScreenerResultItem[];
  summary: ScreenerSummary;
  last_refreshed?: string | null;
}

export interface ScreenerRefreshResponse {
  tickers_fetched: number;
  tickers_failed: string[];
  last_refreshed: string;
  duration_seconds: number;
  universe_size: number;
}

// Preset metadata returned by GET /api/screener/presets
export interface PresetMeta {
  name: string;
  horizon: Horizon;
  description: string;
  recommended_account?: "PEA" | "CTO" | null;
  pea_warning?: boolean | null;
}

// ---------------------------------------------------------------------------
// Portfolio
// ---------------------------------------------------------------------------

export interface AddPositionRequest {
  ticker: string;
  quantity: number;
  buy_price: number;
  buy_date?: string;
  account_type: "pea" | "pea_pme" | "cto";
  notes?: string;
}

export interface UpdatePositionRequest {
  quantity?: number;
  buy_price?: number;
  buy_date?: string;
  notes?: string;
}

export interface PortfolioPosition {
  id: string;
  ticker: string;
  name?: string | null;
  sector?: string | null;
  country?: string | null;
  account_type: string;
  quantity: number;
  buy_price: number;
  buy_date?: string | null;
  current_price?: number | null;
  market_value?: number | null;
  cost_basis?: number | null;
  gain_loss?: number | null;
  gain_loss_pct?: number | null;
  weight_pct?: number | null;
  pe?: number | null;
  pb?: number | null;
  ps?: number | null;
  roe?: number | null;
  roa?: number | null;
  roic?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  revenue_growth?: number | null;
  div_yield?: number | null;
  score_lt?: number | null;
  score_mt?: number | null;
  score_st?: number | null;
  signal_lt?: string | null;
  signal_mt?: string | null;
  signal_st?: string | null;
  piotroski_f?: number | null;
  altman_z?: number | null;
  graham_number?: number | null;
  graham_mos?: number | null;
  dcf_mos_mid?: number | null;
  pea_eligible?: boolean | null;
  pea_pme_eligible?: boolean | null;
  analyst_rating?: string | null;
  analyst_target_price?: number | null;
  notes?: string | null;
  forward_pe?: number | null;
  peg?: number | null;
  fifty_two_week_high_pct?: number | null;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  position_count: number;
  avg_score_lt?: number | null;
  sector_allocation: Record<string, number>;
  country_allocation: Record<string, number>;
  signal_distribution: Record<string, number>;
  pea_value: number;
  cto_value: number;
}

export interface PortfolioResponse {
  positions: PortfolioPosition[];
  summary: PortfolioSummary;
  last_refreshed: string;
  horizon: string;
}

// ---------------------------------------------------------------------------
// Watchlist
// ---------------------------------------------------------------------------

export interface AddWatchlistRequest {
  ticker: string;
  notes?: string;
}

export interface WatchlistItem {
  id: string;
  ticker: string;
  name?: string | null;
  sector?: string | null;
  country?: string | null;
  added_date?: string | null;
  notes?: string | null;
  current_price?: number | null;
  pe?: number | null;
  pb?: number | null;
  roe?: number | null;
  score_lt?: number | null;
  score_mt?: number | null;
  score_st?: number | null;
  signal_lt?: string | null;
  signal_mt?: string | null;
  signal_st?: string | null;
  piotroski_f?: number | null;
  altman_z?: number | null;
  graham_number?: number | null;
  graham_mos?: number | null;
  dcf_mos_mid?: number | null;
  pea_eligible?: boolean | null;
  pea_pme_eligible?: boolean | null;
  analyst_rating?: string | null;
  analyst_target_price?: number | null;
  forward_pe?: number | null;
  peg?: number | null;
  fifty_two_week_high_pct?: number | null;
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  last_refreshed: string;
}

// ---------------------------------------------------------------------------
// Market config
// ---------------------------------------------------------------------------

export interface MarketConfig {
  weights: Record<string, number>;
  horizon_block: Record<string, unknown>;
  preset_list: string[];
}
