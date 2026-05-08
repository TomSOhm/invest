"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { Horizon, ScreenerRequest, ScreenerResponse } from "@/lib/types";

export function useScreener() {
  const [results, setResults] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runScreen = useCallback(async (req: ScreenerRequest) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<ScreenerResponse>("/api/screener/run", req);
      setResults(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Screener failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const runPreset = useCallback(
    async (name: string, peaOnly = false, limit = 50) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.post<ScreenerResponse>(
          `/api/screener/preset/${name}`,
          { pea_only: peaOnly, limit }
        );
        setResults(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Preset screener failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const scoreTickers = useCallback(
    async (tickers: string[], horizon: Horizon = "long_term") => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.post<ScreenerResponse>("/api/screener/tickers", {
          tickers,
          horizon,
        });
        setResults(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Ticker scoring failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return {
    results,
    loading,
    error,
    runScreen,
    runPreset,
    scoreTickers,
  };
}
