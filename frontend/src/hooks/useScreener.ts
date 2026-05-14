"use client";

import { useState, useCallback } from "react";
import { api, refreshScreenerUniverse } from "@/lib/api";
import type {
  DataSource,
  Horizon,
  ScreenerRefreshResponse,
  ScreenerRequest,
  ScreenerResponse,
} from "@/lib/types";

export function useScreener() {
  const [results, setResults] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);

  const runScreen = useCallback(async (req: ScreenerRequest) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<ScreenerResponse>("/api/screener/run", req);
      setResults(res);
      if (res.last_refreshed) setLastRefreshed(res.last_refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Screener failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const runPreset = useCallback(
    async (
      name: string,
      peaOnly = false,
      limit = 50,
      source: DataSource = "hybrid"
    ) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.post<ScreenerResponse>(
          `/api/screener/preset/${name}?source=${source}`,
          { pea_only: peaOnly, top_n: limit }
        );
        setResults(res);
        if (res.last_refreshed) setLastRefreshed(res.last_refreshed);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Preset screener failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const scoreTickers = useCallback(
    async (
      tickers: string[],
      horizon: Horizon = "long_term",
      source: DataSource = "hybrid"
    ) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.post<ScreenerResponse>(
          `/api/screener/tickers?source=${source}`,
          { tickers, horizon }
        );
        setResults(res);
        if (res.last_refreshed) setLastRefreshed(res.last_refreshed);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Ticker scoring failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const refresh = useCallback(
    async (
      source: DataSource = "hybrid"
    ): Promise<ScreenerRefreshResponse | null> => {
      setRefreshing(true);
      setError(null);
      try {
        const res = await refreshScreenerUniverse(source);
        setLastRefreshed(res.last_refreshed);
        return res;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Refresh failed");
        return null;
      } finally {
        setRefreshing(false);
      }
    },
    []
  );

  return {
    results,
    loading,
    refreshing,
    error,
    lastRefreshed,
    runScreen,
    runPreset,
    scoreTickers,
    refresh,
  };
}
