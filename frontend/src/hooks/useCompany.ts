"use client";

import { useState, useCallback } from "react";
import { fetchCompanyDetail } from "@/lib/api";
import type { CompanyDetail, DataSource } from "@/lib/types";

export function useCompany() {
  const [data, setData] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(
    async (ticker: string, source: DataSource = "hybrid") => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchCompanyDetail(ticker, source);
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load company data");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { data, loading, error, fetch };
}
