"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { WatchlistResponse, WatchlistItem, AddWatchlistRequest } from "@/lib/types";

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

  const addItem = useCallback(
    async (req: AddWatchlistRequest): Promise<WatchlistItem | null> => {
      try {
        const item = await api.post<WatchlistItem>("/api/watchlist", req);
        await fetch();
        return item;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add item");
        return null;
      }
    },
    [fetch]
  );

  const removeItem = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        await api.del<{ ok: boolean }>(`/api/watchlist/${id}`);
        await fetch();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to remove item");
        return false;
      }
    },
    [fetch]
  );

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

  useEffect(() => {
    fetch();
  }, [fetch]);

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
