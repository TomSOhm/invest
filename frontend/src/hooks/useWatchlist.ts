"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  WatchlistResponse,
  WatchlistItem,
  AddWatchlistRequest,
} from "@/lib/types";

export function useWatchlist() {
  const [data, setData] = useState<WatchlistResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<WatchlistResponse>("/api/watchlist");
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load watchlist");
    } finally {
      setLoading(false);
    }
  }, []);

  // Optimistic add: backend returns the new item already enriched with
  // score_lt/mt/st and the rest. Splice into local state instead of
  // re-fetching the full list.
  const addItem = useCallback(
    async (req: AddWatchlistRequest): Promise<WatchlistItem | null> => {
      try {
        const item = await api.post<WatchlistItem>("/api/watchlist", req);
        setData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            items: [...prev.items, item],
          };
        });
        return item;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add item");
        return null;
      }
    },
    []
  );

  const removeItem = useCallback(async (id: string): Promise<boolean> => {
    try {
      await api.del<{ ok: boolean }>(`/api/watchlist/${id}`);
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.filter((i) => i.id !== id),
        };
      });
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove item");
      return false;
    }
  }, []);

  // Only path to live FMP / yfinance data. Backend invalidates the ticker
  // cache before re-fetching.
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<WatchlistResponse>("/api/watchlist/refresh");
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh watchlist");
    } finally {
      setLoading(false);
    }
  }, []);

  // Mount-once. Add/remove/horizon flips never refetch.
  useEffect(() => {
    fetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    data,
    loading,
    error,
    fetch,
    addItem,
    removeItem,
    refresh,
  };
}
