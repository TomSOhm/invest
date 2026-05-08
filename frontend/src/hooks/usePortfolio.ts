"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  Horizon,
  PortfolioResponse,
  PortfolioSummary,
  AddPositionRequest,
  UpdatePositionRequest,
  PortfolioPosition,
} from "@/lib/types";

// Recompute the summary card numbers from a positions array.
// Used on optimistic add/update/remove so the cards update instantly without
// hitting the backend. Sector / country / account splits are derived from
// the same positions; weights are repaired in-line.
function recomputeSummary(positions: PortfolioPosition[]): PortfolioSummary {
  const total_value = positions.reduce((s, p) => s + (p.market_value ?? 0), 0);
  const total_cost = positions.reduce((s, p) => s + (p.cost_basis ?? 0), 0);
  const total_gain_loss = total_value - total_cost;
  const total_gain_loss_pct = total_cost > 0 ? total_gain_loss / total_cost : 0;

  const scored = positions.filter((p) => typeof p.score_lt === "number");
  const avg_score_lt = scored.length
    ? scored.reduce((s, p) => s + (p.score_lt ?? 0), 0) / scored.length
    : null;

  const signal_distribution = positions.reduce<Record<string, number>>((acc, p) => {
    const key = p.signal_lt ?? "Unknown";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  const sector_allocation = positions.reduce<Record<string, number>>((acc, p) => {
    const key = p.sector ?? "Unknown";
    acc[key] = (acc[key] ?? 0) + (p.market_value ?? 0);
    return acc;
  }, {});

  const country_allocation = positions.reduce<Record<string, number>>((acc, p) => {
    const key = p.country ?? "Unknown";
    acc[key] = (acc[key] ?? 0) + (p.market_value ?? 0);
    return acc;
  }, {});

  const pea_value = positions
    .filter((p) => p.account_type === "pea" || p.account_type === "pea_pme")
    .reduce((s, p) => s + (p.market_value ?? 0), 0);
  const cto_value = positions
    .filter((p) => p.account_type === "cto")
    .reduce((s, p) => s + (p.market_value ?? 0), 0);

  return {
    total_value,
    total_cost,
    total_gain_loss,
    total_gain_loss_pct,
    position_count: positions.length,
    avg_score_lt,
    signal_distribution,
    sector_allocation,
    country_allocation,
    pea_value,
    cto_value,
  };
}

function recomputeWeights(positions: PortfolioPosition[]): PortfolioPosition[] {
  const total = positions.reduce((s, p) => s + (p.market_value ?? 0), 0);
  if (total <= 0) return positions;
  return positions.map((p) => ({
    ...p,
    weight_pct: (p.market_value ?? 0) / total,
  }));
}

export function usePortfolio(initialHorizon: Horizon = "long_term") {
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<Horizon>(initialHorizon);

  // Stable fetch — empty deps so useEffect mount only fires once.
  // Caller can pass an explicit horizon to override the closure default
  // (used by `refresh()` which always uses the current horizon).
  const fetch = useCallback(async (h?: Horizon) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<PortfolioResponse>(
        `/api/portfolio/?horizon=${h ?? "long_term"}`
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, []);

  // Horizon switch is now purely client-side: the response already carries
  // all three score columns per position. We just remember which one to
  // highlight; the page re-renders with the existing data.
  const changeHorizon = useCallback((h: Horizon) => {
    setHorizon(h);
  }, []);

  // Optimistic add: backend POST returns the new position with full scoring.
  // Append to local state and recompute summary/weights client-side.
  const addPosition = useCallback(
    async (req: AddPositionRequest): Promise<PortfolioPosition | null> => {
      try {
        const pos = await api.post<PortfolioPosition>(
          "/api/portfolio/positions",
          req
        );
        setData((prev) => {
          if (!prev) return prev;
          const positions = recomputeWeights([...prev.positions, pos]);
          return {
            ...prev,
            positions,
            summary: recomputeSummary(positions),
          };
        });
        return pos;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to add position");
        return null;
      }
    },
    []
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
        setData((prev) => {
          if (!prev) return prev;
          const positions = recomputeWeights(
            prev.positions.map((p) => (p.id === id ? pos : p))
          );
          return {
            ...prev,
            positions,
            summary: recomputeSummary(positions),
          };
        });
        return pos;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update position");
        return null;
      }
    },
    []
  );

  const removePosition = useCallback(async (id: string): Promise<boolean> => {
    try {
      await api.del<{ ok: boolean }>(`/api/portfolio/positions/${id}`);
      setData((prev) => {
        if (!prev) return prev;
        const positions = recomputeWeights(
          prev.positions.filter((p) => p.id !== id)
        );
        return {
          ...prev,
          positions,
          summary: recomputeSummary(positions),
        };
      });
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove position");
      return false;
    }
  }, []);

  // Refresh hits the backend cache-invalidating endpoint. The only path
  // that pulls live data from FMP / yfinance.
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<PortfolioResponse>(
        `/api/portfolio/refresh?horizon=${horizon}`
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh portfolio");
    } finally {
      setLoading(false);
    }
  }, [horizon]);

  // Mount-once fetch. Empty deps on purpose — horizon flip does not refetch.
  useEffect(() => {
    fetch(initialHorizon);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
