"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  openScreenerRefreshStream,
  refreshScreenerUniverse,
} from "@/lib/api";
import type {
  DataSource,
  Horizon,
  ScreenerRefreshResponse,
  ScreenerRequest,
  ScreenerResponse,
} from "@/lib/types";

export interface RefreshProgress {
  done: number;
  total: number;
}

export function useScreener() {
  const [results, setResults] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] =
    useState<RefreshProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const streamRef = useRef<EventSource | null>(null);

  // Abort any in-flight stream on unmount so a navigation doesn't leave a
  // dangling HTTP connection.
  useEffect(() => {
    return () => {
      streamRef.current?.close();
      streamRef.current = null;
    };
  }, []);

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

  // Streaming refresh: emits progress events while parallel fetch runs. Falls
  // back to the POST endpoint when EventSource is unavailable (test env, some
  // older runtimes).
  const refreshStream = useCallback(
    (source: DataSource = "hybrid"): Promise<ScreenerRefreshResponse | null> => {
      if (typeof window === "undefined" || typeof EventSource === "undefined") {
        return refresh(source);
      }

      // Close any prior stream before opening a new one.
      streamRef.current?.close();
      streamRef.current = null;

      setRefreshing(true);
      setError(null);
      setRefreshProgress({ done: 0, total: 0 });

      return new Promise<ScreenerRefreshResponse | null>((resolve) => {
        const es = openScreenerRefreshStream(source, {
          onStart: ({ total }) => setRefreshProgress({ done: 0, total }),
          onTicker: ({ progress }) => setRefreshProgress(progress),
          onDone: (summary) => {
            setLastRefreshed(summary.last_refreshed);
            setRefreshing(false);
            setRefreshProgress(null);
            streamRef.current = null;
            resolve(summary);
          },
          onError: ({ reason }) => {
            setError(reason || "Stream refresh failed");
            setRefreshing(false);
            setRefreshProgress(null);
            streamRef.current = null;
            resolve(null);
          },
        });
        streamRef.current = es;
      });
    },
    [refresh]
  );

  return {
    results,
    loading,
    refreshing,
    refreshProgress,
    error,
    lastRefreshed,
    runScreen,
    runPreset,
    scoreTickers,
    refresh,
    refreshStream,
  };
}
