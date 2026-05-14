"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { DataSource } from "@/lib/types";
import { DATA_SOURCES } from "@/lib/types";

const STORAGE_KEY = "invest:data_source";
const CHANGE_EVENT = "invest:data_source_change";

function readStored(): DataSource {
  if (typeof window === "undefined") return "hybrid";
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return DATA_SOURCES.includes(raw as DataSource)
    ? (raw as DataSource)
    : "hybrid";
}

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) callback();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

function getServerSnapshot(): DataSource {
  return "hybrid";
}

/**
 * Reads + persists the global data source choice in localStorage.
 * Cross-tab sync via the `storage` event; same-tab sync via a custom event.
 */
export function useDataSource(): {
  source: DataSource;
  setSource: (s: DataSource) => void;
} {
  const source = useSyncExternalStore(subscribe, readStored, getServerSnapshot);

  const setSource = useCallback((s: DataSource) => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, s);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return { source, setSource };
}
