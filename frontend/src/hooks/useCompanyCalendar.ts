"use client";

import { useEffect, useState } from "react";
import { fetchCompanyCalendar } from "@/lib/api";
import type { CompanyCalendar, DataSource } from "@/lib/types";

type FetchResult = {
  key: string;
  data: CompanyCalendar | null;
  error: string | null;
};

export function useCompanyCalendar(
  ticker: string,
  source: DataSource = "hybrid",
): { data: CompanyCalendar | null; loading: boolean; error: string | null } {
  const key = `${ticker}|${source}`;
  const [result, setResult] = useState<FetchResult>({
    key: "",
    data: null,
    error: null,
  });

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    fetchCompanyCalendar(ticker, source)
      .then((res) => {
        if (!cancelled) setResult({ key, data: res, error: null });
      })
      .catch((e) => {
        if (!cancelled)
          setResult({
            key,
            data: null,
            error: e instanceof Error ? e.message : "Failed to load calendar",
          });
      });
    return () => {
      cancelled = true;
    };
    // `key` is derived from ticker+source and intentionally excluded from
    // the dep array to avoid double-firing the effect on each input change.
  }, [ticker, source]);

  const ready = result.key === key;
  return {
    data: ready ? result.data : null,
    loading: !!ticker && !ready,
    error: ready ? result.error : null,
  };
}
