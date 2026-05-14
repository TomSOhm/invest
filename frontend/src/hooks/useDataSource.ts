"use client";

import { useCallback, useEffect, useState } from "react";
import type { DataSource } from "@/lib/types";
import { DATA_SOURCES } from "@/lib/types";

const STORAGE_KEY = "invest:data_source";

function readStored(): DataSource {
  if (typeof window === "undefined") return "hybrid";
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return DATA_SOURCES.includes(raw as DataSource)
    ? (raw as DataSource)
    : "hybrid";
}

/**
 * Reads + persists the global data source choice in localStorage.
 * Cross-tab sync via the `storage` event so every page reacts to a change.
 */
export function useDataSource(): {
  source: DataSource;
  setSource: (s: DataSource) => void;
} {
  const [source, setSourceState] = useState<DataSource>("hybrid");

  useEffect(() => {
    setSourceState(readStored());
    const onStorage = (e: StorageEvent) => {
      if (
        e.key === STORAGE_KEY &&
        DATA_SOURCES.includes(e.newValue as DataSource)
      ) {
        setSourceState(e.newValue as DataSource);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setSource = useCallback((s: DataSource) => {
    setSourceState(s);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, s);
    }
  }, []);

  return { source, setSource };
}
