import type {
  ApiResponse,
  BotStatus,
  FillList,
  MarketStatus,
  OrderCancelResponse,
  OrderList,
  OrderModifyResponse,
  PositionList,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () => request<BotStatus>("/status"),
  getPositions: (limit = 50) =>
    request<PositionList>(`/positions?limit=${limit}`),
  getOrders: (limit = 100, status?: string) => {
    const qs = status ? `?limit=${limit}&status=${status}` : `?limit=${limit}`;
    return request<OrderList>(`/orders${qs}`);
  },
  pause: () => request<ApiResponse>("/control/pause", { method: "POST" }),
  resume: () => request<ApiResponse>("/control/resume", { method: "POST" }),
  kill: () => request<ApiResponse>("/control/kill", { method: "POST" }),

  // T056 — 체결·마켓·주문관리
  getFills: (count = 100) => request<FillList>(`/trades?count=${count}`),
  getMarketStatus: () => request<MarketStatus>("/market-status"),
  cancelOrder: (orderId: string) =>
    request<OrderCancelResponse>(`/orders/${orderId}/cancel`, {
      method: "POST",
    }),
  modifyOrder: (
    orderId: string,
    body: {
      order_type: string;
      quantity?: number;
      price?: number;
      confirm_high_value?: boolean;
    },
  ) =>
    request<OrderModifyResponse>(`/orders/${orderId}/modify`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// WebSocket URL: vite proxy /stream → ws://localhost:8000/stream
export function createStreamSocket(
  onMessage: (msg: unknown) => void,
): WebSocket {
  const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/stream`;
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data as string));
    } catch {
      // non-JSON frame 무시
    }
  };
  return ws;
}
