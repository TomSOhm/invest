"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { CompanyDetail } from "@/lib/types";

export function useCompany() {
  const [data, setData] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (ticker: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<CompanyDetail>(`/api/company/${ticker.toUpperCase()}`);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load company data");
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetch };
}
