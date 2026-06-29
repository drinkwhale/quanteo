// Control API 응답 타입 (core/api/models.py 와 1:1 대응)

export interface BotStatus {
  running: boolean;
  halt_level: "none" | "reduce" | "pause" | "kill";
  env: "vps" | "prod";
  market: "domestic" | "overseas";
  uptime_seconds: number;
  started_at: string | null;
}

export interface PositionItem {
  symbol: string;
  market: string;
  env: string;
  qty: number;
  avg_price: number;
  book_value: number;
  opened_at: string;
  updated_at: string;
}

export interface PositionList {
  total: number;
  items: PositionItem[];
}

export interface OrderItem {
  client_order_id: string;
  kis_order_id: string | null;
  symbol: string;
  market: string;
  env: string;
  side: "BUY" | "SELL";
  order_type: string;
  qty: number;
  price: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface OrderList {
  total: number;
  items: OrderItem[];
}

export interface ApiResponse {
  success: boolean;
  message: string;
}

export interface StreamMessage {
  event_type: string;
  payload: unknown;
  timestamp: string;
  source: string;
}

// T056 — 체결 내역
export interface FillItem {
  symbol: string;
  price: number;
  volume: number;
  timestamp: string;
  currency: string;
  side: "BUY" | "SELL" | null;
}

export interface FillList {
  total: number;
  items: FillItem[];
}

// T056 — 마켓 상태
export interface MarketDayStatus {
  market: string;
  is_open: boolean;
  today_date: string;
  open_time: string | null;
  close_time: string | null;
}

export interface MarketStatus {
  markets: MarketDayStatus[];
}

// T056 — 주문 취소·정정 응답
export interface OrderCancelResponse {
  success: boolean;
  order_id: string;
  message: string;
}

export interface OrderModifyResponse {
  success: boolean;
  order_id: string;
  message: string;
}
