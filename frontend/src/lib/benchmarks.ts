export interface BenchmarkOption {
  key: string;
  label: string;
  ticker: string | null;
}

export const BENCHMARK_OPTIONS: BenchmarkOption[] = [
  { key: "none", label: "None", ticker: null },
  { key: "sp500", label: "S&P 500", ticker: "^GSPC" },
  { key: "cac40", label: "CAC 40", ticker: "^FCHI" },
  { key: "ftse100", label: "FTSE 100", ticker: "^FTSE" },
  { key: "dax", label: "DAX", ticker: "^GDAXI" },
  { key: "stoxx600", label: "STOXX 600", ticker: "^STOXX" },
  { key: "nasdaq", label: "Nasdaq Comp", ticker: "^IXIC" },
];
