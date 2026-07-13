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

// core/api/routes/orders.py의 _VALID_STATUSES와 1:1 대응 — "open"은 Toss
// list_orders(status="OPEN") 조회 파라미터일 뿐 실제 주문 상태값이 아니므로
// 여기 포함하지 않는다. 이 유니온에 값을 추가하면 OrdersTable.tsx의
// Record<OrderStatus, ...> 매핑들이 컴파일 에러로 누락을 잡아준다.
export type OrderStatus =
  "pending" | "submitted" | "partial" | "filled" | "cancelled" | "rejected";

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
  status: OrderStatus;
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

// 종목명 조회 — 심볼 코드 대신 종목명 표시용 (영업일 단위 갱신, 세션당 1회 캐시)
export interface StockNameItem {
  symbol: string;
  name: string;
  market: string;
}

export interface StockNameList {
  items: StockNameItem[];
}

// 전일 종가 대비 당일 등락. amount/rate는 항상 함께 있거나 함께 없다(캔들
// 조회 실패 시 전체가 null) — 그 불변식을 표현하려고 독립된 nullable 필드
// 두 개 대신 하나의 nullable 하위 타입으로 감쌌다.
export interface DayChange {
  amount: number;
  rate: number;
}

// 계좌 요약 — 실계좌 평가금액·평가손익 (Toss holdings 그대로 반영)
// profit_loss(_rate)는 매입가 기준 누적 손익, day_change는 전일 종가
// 기준 당일 등락 — 서로 다른 축이니 섞어 쓰지 말 것(과거에 이 버그가 있었음).
export interface BalanceItem {
  symbol: string;
  symbol_name: string;
  qty: number;
  avg_price: number;
  current_price: number;
  eval_amount: number;
  profit_loss: number;
  profit_loss_rate: number;
  day_change: DayChange | null;
  market: string;
}

export interface BalanceInfo {
  items: BalanceItem[];
  total_eval_amount_krw: number;
  total_profit_loss_krw: number;
  deposit: number;
}

// 주요 지수 시세 — Toss API 미지원, 외부 소스(Yahoo Finance) 조회
export interface IndexQuoteItem {
  key: string;
  label: string;
  price: number;
  change: number;
  change_rate: number;
  currency: string;
}

export interface IndexQuoteResponse {
  items: IndexQuoteItem[];
}
