import type {
  ChartPeriod,
  CompanyCalendar,
  CompanyDetail,
  DataSource,
  Horizon,
  PortfolioResponse,
  PresetMeta,
  PriceHistoryResponse,
  ScreenerRefreshResponse,
  ScreenerResponse,
  ScreenerStreamDoneEvent,
  ScreenerStreamErrorEvent,
  ScreenerStreamStartEvent,
  ScreenerStreamTickerEvent,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        message =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // ignore JSON parse error
    }
    throw new ApiError(message, res.status);
  }

  return res.json() as Promise<T>;
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: "GET" });
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  del<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};

// ---------------------------------------------------------------------------
// Typed helpers (M11)
// ---------------------------------------------------------------------------

export async function fetchScreenerPresets(): Promise<PresetMeta[]> {
  return api.get<PresetMeta[]>("/api/screener/presets");
}

export async function fetchHorizonScreening(
  preset: string,
  peaOnly = false,
  limit = 50,
  source: DataSource = "hybrid"
): Promise<ScreenerResponse> {
  return api.post<ScreenerResponse>(
    `/api/screener/preset/${preset}?source=${source}`,
    { pea_only: peaOnly, top_n: limit }
  );
}

export async function fetchCompanyDetail(
  ticker: string,
  source: DataSource = "hybrid"
): Promise<CompanyDetail> {
  return api.get<CompanyDetail>(
    `/api/company/${ticker.toUpperCase()}?source=${source}`
  );
}

export async function fetchPortfolio(
  horizon: Horizon = "long_term",
  source: DataSource = "hybrid"
): Promise<PortfolioResponse> {
  return api.get<PortfolioResponse>(
    `/api/portfolio/?horizon=${horizon}&source=${source}`
  );
}

export async function refreshScreenerUniverse(
  source: DataSource = "hybrid"
): Promise<ScreenerRefreshResponse> {
  return api.post<ScreenerRefreshResponse>(
    `/api/screener/refresh?source=${source}`
  );
}

export interface ScreenerStreamHandlers {
  onStart?: (e: ScreenerStreamStartEvent) => void;
  onTicker?: (e: ScreenerStreamTickerEvent) => void;
  onDone?: (e: ScreenerStreamDoneEvent) => void;
  onError?: (e: ScreenerStreamErrorEvent) => void;
}

/**
 * Open an EventSource on GET /api/screener/refresh/stream and dispatch each
 * named SSE event to the matching handler. The returned EventSource is
 * closed automatically on `done` / `error` events; callers should also call
 * `.close()` on unmount to abort an in-flight stream.
 */
export function openScreenerRefreshStream(
  source: DataSource,
  handlers: ScreenerStreamHandlers
): EventSource {
  const es = new EventSource(
    `${BASE_URL}/api/screener/refresh/stream?source=${source}`
  );

  es.addEventListener("start", (ev) => {
    handlers.onStart?.(JSON.parse((ev as MessageEvent).data));
  });
  es.addEventListener("ticker", (ev) => {
    handlers.onTicker?.(JSON.parse((ev as MessageEvent).data));
  });
  es.addEventListener("done", (ev) => {
    handlers.onDone?.(JSON.parse((ev as MessageEvent).data));
    es.close();
  });
  // Server emits a named "error" event with a JSON payload on fatal errors.
  // EventSource also fires its built-in "error" listener on socket failures;
  // distinguish by presence of MessageEvent.data.
  es.addEventListener("error", (ev) => {
    const data = (ev as MessageEvent).data;
    if (typeof data === "string" && data.length > 0) {
      try {
        handlers.onError?.(JSON.parse(data));
      } catch {
        handlers.onError?.({ reason: data });
      }
      es.close();
    } else if (es.readyState === EventSource.CLOSED) {
      handlers.onError?.({ reason: "connection closed" });
    }
  });

  return es;
}

export async function fetchPriceHistory(
  ticker: string,
  period: ChartPeriod = "1Y",
  benchmark: string | null = null
): Promise<PriceHistoryResponse> {
  const benchParam = benchmark
    ? `&benchmark=${encodeURIComponent(benchmark)}`
    : "";
  return api.get<PriceHistoryResponse>(
    `/api/company/${ticker.toUpperCase()}/price-history?period=${period}${benchParam}`
  );
}

export async function fetchCompanyCalendar(
  ticker: string,
  source: DataSource = "hybrid"
): Promise<CompanyCalendar> {
  return api.get<CompanyCalendar>(
    `/api/company/${ticker.toUpperCase()}/calendar?source=${source}`
  );
}

export { ApiError };
