// Portfolio
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
  name: string;
  sector: string;
  country: string;
  account_type: string;
  quantity: number;
  buy_price: number;
  buy_date: string | null;
  current_price: number;
  market_value: number;
  cost_basis: number;
  gain_loss: number;
  gain_loss_pct: number;
  weight_pct: number;
  pe: number | null;
  pb: number | null;
  ps: number | null;
  roe: number | null;
  roa: number | null;
  roic: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  revenue_growth: number | null;
  div_yield: number | null;
  composite_score: number | null;
  signal: string | null;
  piotroski_f: number | null;
  altman_z: number | null;
  graham_number: number | null;
  graham_mos: number | null;
  valuation_score: number | null;
  health_score: number | null;
  profitability_score: number | null;
  growth_score: number | null;
  shareholder_score: number | null;
  risk_score: number | null;
  pea_eligible: boolean;
  pea_pme_eligible: boolean;
  notes: string | null;
  forward_pe: number | null;
  peg: number | null;
  analyst_rating: string | null;
  analyst_target_price: number | null;
  fifty_two_week_high_pct: number | null;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  position_count: number;
  avg_composite_score: number;
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
}

// Watchlist
export interface AddWatchlistRequest {
  ticker: string;
  notes?: string;
}

export interface WatchlistItem {
  id: string;
  ticker: string;
  name: string;
  sector: string;
  country: string;
  added_date: string;
  notes: string | null;
  current_price: number;
  pe: number | null;
  pb: number | null;
  roe: number | null;
  composite_score: number | null;
  signal: string | null;
  piotroski_f: number | null;
  altman_z: number | null;
  graham_number: number | null;
  graham_mos: number | null;
  pea_eligible: boolean;
  pea_pme_eligible: boolean;
  analyst_rating: string | null;
  analyst_target_price: number | null;
  forward_pe: number | null;
  peg: number | null;
  fifty_two_week_high_pct: number | null;
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  last_refreshed: string;
}

// Screener
export interface ScreenerFilters {
  min_market_cap?: number;
  max_market_cap?: number;
  min_pe?: number;
  max_pe?: number;
  min_roe?: number;
  min_current_ratio?: number;
  max_debt_equity?: number;
  min_interest_coverage?: number;
  min_operating_margin?: number;
  min_fcf?: number;
  min_composite_score?: number;
  min_div_yield?: number;
  max_payout_ratio?: number;
  min_revenue_growth?: number;
}

export interface ScreenerRequest {
  filters: ScreenerFilters;
  pea_only: boolean;
  sort_by: string;
  sort_desc: boolean;
  limit: number;
}

export interface ScreenerResultItem {
  ticker: string;
  name: string;
  sector: string;
  country: string;
  price: number;
  market_cap: number;
  composite_score: number;
  signal: string;
  pe: number | null;
  pb: number | null;
  roe: number | null;
  div_yield: number | null;
  revenue_growth: number | null;
  piotroski_f: number;
  altman_z: number | null;
  graham_mos: number | null;
  pea_eligible: boolean;
  valuation_score: number;
  health_score: number;
  profitability_score: number;
  growth_score: number;
}

export interface ScreenerSummary {
  total_screened: number;
  total_passed: number;
  avg_score: number;
  signal_distribution: Record<string, number>;
  sector_distribution: Record<string, number>;
}

export interface ScreenerResponse {
  results: ScreenerResultItem[];
  summary: ScreenerSummary;
  filters_applied: Record<string, unknown>;
}

// Company
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
}

export interface CompanyMetrics {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  country: string;
  exchange: string;
  price: number;
  market_cap: number;
  enterprise_value: number | null;
  pe: number | null;
  forward_pe: number | null;
  pb: number | null;
  ps: number | null;
  pfcf: number | null;
  ev_ebitda: number | null;
  ev_sales: number | null;
  peg: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  fcf_margin: number | null;
  roe: number | null;
  roa: number | null;
  roic: number | null;
  revenue_growth: number | null;
  current_ratio: number | null;
  debt_equity: number | null;
  interest_coverage: number | null;
  div_yield: number | null;
  payout_ratio: number | null;
  beta: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  fifty_two_week_high_pct: number | null;
  insider_pct: number | null;
  institutional_pct: number | null;
  short_pct_float: number | null;
  earnings_surprise_pct: number | null;
}

export interface ScoringBreakdown {
  composite_score: number;
  signal: string;
  valuation_score: number;
  health_score: number;
  profitability_score: number;
  growth_score: number;
  shareholder_score: number;
  risk_score: number;
  piotroski_f: number;
  altman_z: number | null;
  graham_number: number | null;
  graham_mos: number | null;
  scoring_weights: Record<string, number>;
}

export interface CompanyDetail {
  metrics: CompanyMetrics;
  scoring: ScoringBreakdown;
  analyst: AnalystRatings | null;
  pea_eligible: boolean;
  pea_pme_eligible: boolean;
  data_source: string;
  last_updated: string;
}

export type Signal = "Strong Buy" | "Buy" | "Hold" | "Sell" | "Strong Sell";
