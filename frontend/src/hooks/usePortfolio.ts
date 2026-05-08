"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  Horizon,
  PortfolioResponse,
  AddPositionRequest,
  UpdatePositionRequest,
  PortfolioPosition,
} from "@/lib/types";

export function usePortfolio(initialHorizon: Horizon = "long_term") {
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<Horizon>(initialHorizon);

  const fetch = useCallback(
    async (h: Horizon = horizon) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<PortfolioResponse>(
          `/api/portfolio/?horizon=${h}`
        );
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load portfolio");
      } finally {
        setLoading(false);
      }
    },
    [horizon]
  );

  const changeHorizon = useCallback(
    (h: Horizon) => {
      setHorizon(h);
      fetch(h);
    },
    [fetch]
  );

  const addPosition = useCallback(
    async (req: AddPositionRequest): Promise<PortfolioPosition | null> => {
      try {
        const pos = await api.post<PortfolioPosition>(
          "/api/portfolio/positions",
          req
        );
        await fetch();
        return pos;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add position");
        return null;
      }
    },
    [fetch]
  );

  const updatePosition = useCallback(
    async (
      id: string,
      req: UpdatePositionRequest
    ): Promise<PortfolioPosition | null> => {
      try {
        const pos = await api.put<PortfolioPosition>(
          `/api/portfolio/positions/${id}`,
          req
        );
        await fetch();
        return pos;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update position");
        return null;
      }
    },
    [fetch]
  );

  const removePosition = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        await api.del<{ ok: boolean }>(`/api/portfolio/positions/${id}`);
        await fetch();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to remove position");
        return false;
      }
    },
    [fetch]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<PortfolioResponse>("/api/portfolio/refresh");
      setData(res);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to refresh portfolio"
      );
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
    horizon,
    changeHorizon,
    fetch,
    addPosition,
    updatePosition,
    removePosition,
    refresh,
  };
}
