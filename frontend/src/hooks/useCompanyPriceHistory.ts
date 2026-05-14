"use client";

import { useEffect, useState } from "react";
import { fetchPriceHistory } from "@/lib/api";
import type { ChartPeriod, PriceHistoryResponse } from "@/lib/types";

export function useCompanyPriceHistory(
  ticker: string,
  period: ChartPeriod,
  benchmark: string | null,
): { data: PriceHistoryResponse | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<PriceHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchPriceHistory(ticker, period, benchmark)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load price history");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [ticker, period, benchmark]);

  return { data, loading, error };
}
