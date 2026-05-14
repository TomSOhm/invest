"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  AddWatchlistRequest,
  DataSource,
  WatchlistItem,
  WatchlistResponse,
} from "@/lib/types";

export function useWatchlist(source: DataSource = "hybrid") {
  const [data, setData] = useState<WatchlistResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<WatchlistResponse>(
        `/api/watchlist/?source=${source}`,
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load watchlist");
    } finally {
      setLoading(false);
    }
  }, [source]);

  const addItem = useCallback(
    async (req: AddWatchlistRequest): Promise<WatchlistItem | null> => {
      try {
        const item = await api.post<WatchlistItem>(
          `/api/watchlist/?source=${source}`,
          req,
        );
        setData((prev) => {
          if (!prev) return prev;
          return { ...prev, items: [...prev.items, item] };
        });
        return item;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add item");
        return null;
      }
    },
    [source],
  );

  const removeItem = useCallback(async (id: string): Promise<boolean> => {
    try {
      await api.del<{ ok: boolean }>(`/api/watchlist/${id}`);
      setData((prev) => {
        if (!prev) return prev;
        return { ...prev, items: prev.items.filter((i) => i.id !== id) };
      });
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove item");
      return false;
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<WatchlistResponse>(
        `/api/watchlist/refresh?source=${source}`,
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh watchlist");
    } finally {
      setLoading(false);
    }
  }, [source]);

  // Refetch when source changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/set-state-in-effect
  useEffect(() => { fetch(); }, [source]);

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
