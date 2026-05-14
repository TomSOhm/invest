"use client";

import { useEffect, useState } from "react";
import { fetchPriceHistory } from "@/lib/api";
import type { ChartPeriod, PriceHistoryResponse } from "@/lib/types";

type FetchResult = {
  key: string;
  data: PriceHistoryResponse | null;
  error: string | null;
};

export function useCompanyPriceHistory(
  ticker: string,
  period: ChartPeriod,
  benchmark: string | null,
): { data: PriceHistoryResponse | null; loading: boolean; error: string | null } {
  const key = `${ticker}|${period}|${benchmark ?? ""}`;
  const [result, setResult] = useState<FetchResult>({
    key: "",
    data: null,
    error: null,
  });

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    fetchPriceHistory(ticker, period, benchmark)
      .then((res) => {
        if (!cancelled) setResult({ key, data: res, error: null });
      })
      .catch((e) => {
        if (!cancelled)
          setResult({
            key,
            data: null,
            error: e instanceof Error ? e.message : "Failed to load price history",
          });
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, period, benchmark, key]);

  const ready = result.key === key;
  return {
    data: ready ? result.data : null,
    loading: !!ticker && !ready,
    error: ready ? result.error : null,
  };
}
