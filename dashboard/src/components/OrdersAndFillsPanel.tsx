import { useId, useMemo, useState } from "react";
import { api } from "../api/client";
import { TIMESTAMP_CELL_CLASS } from "../lib/utils";
import type { OrderItem, OrderStatus, FillItem } from "../api/types";
import { StockCell } from "./StockCell";

const STATUS_COLOR: Record<OrderStatus, string> = {
  pending: "text-warning",
  submitted: "text-accent",
  partial: "text-accent",
  filled: "text-positive",
  cancelled: "text-muted",
  rejected: "text-negative",
};

const CANCELLABLE_STATUSES: ReadonlySet<OrderStatus> = new Set([
  "pending",
  "submitted",
  "partial",
]);

type OrderTab = "pending" | "completed";
type MainTab = "orders" | "fills";

const STATUS_TAB: Record<OrderStatus, OrderTab> = {
  pending: "pending",
  submitted: "pending",
  partial: "pending",
  filled: "completed",
  cancelled: "completed",
  rejected: "completed",
};

type VisibleTab = OrderTab | "conditional";

const ORDER_TAB_LABEL: Record<VisibleTab, string> = {
  pending: "대기",
  completed: "완료",
  conditional: "조건주문",
};

interface Props {
  orders: OrderItem[];
  fills: FillItem[];
  ordersError?: string | null;
  fillsError?: string | null;
  ordersTotal: number;
  fillsTotal: number;
  onRefetch?: () => void;
  stockNames: Map<string, string>;
}

export function OrdersAndFillsPanel({
  orders,
  fills,
  ordersError,
  fillsError,
  ordersTotal,
  fillsTotal,
  onRefetch,
  stockNames,
}: Props) {
  const [mainTab, setMainTab] = useState<MainTab>("orders");
  const [orderTab, setOrderTab] = useState<VisibleTab>("pending");
  const [actionError, setActionError] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const tabPanelId = useId();

  async function handleCancel(orderId: string) {
    setLoading(orderId);
    setActionError(null);
    try {
      await api.cancelOrder(orderId);
      onRefetch?.();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "취소 실패");
    } finally {
      setLoading(null);
    }
  }

  const grouped = useMemo(() => {
    const result: Record<OrderTab, OrderItem[]> = {
      pending: [],
      completed: [],
    };
    for (const o of orders) {
      const t = STATUS_TAB[o.status];
      if (t === undefined) {
        console.warn(
          `[OrdersAndFillsPanel] 알 수 없는 주문 상태 — 목록에 표시되지 않습니다: status=${o.status} client_order_id=${o.client_order_id}`,
        );
        continue;
      }
      result[t].push(o);
    }
    return result;
  }, [orders]);

  const orderCounts = useMemo(
    () => ({
      pending: grouped.pending.length,
      completed: grouped.completed.length,
      conditional: 0,
    }),
    [grouped],
  );

  const visibleOrders = orderTab === "conditional" ? [] : grouped[orderTab];

  const orderEmptyMessage =
    orderTab === "conditional"
      ? "조건주문 기능은 아직 지원되지 않음"
      : "주문 내역 없음";

  return (
    <>
      {/* 메인 탭 — Orders / Fills */}
      <div
        role="tablist"
        aria-label="주문·체결 탭"
        className="flex gap-1 px-4 pt-3 border-b border-border"
      >
        {(["orders", "fills"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`${tabPanelId}-main-tab-${tab}`}
            aria-selected={mainTab === tab}
            aria-controls={`${tabPanelId}-main-panel`}
            onClick={() => setMainTab(tab)}
            className={`px-3 py-2.5 text-sm font-sans border-b-2 transition-colors ${
              mainTab === tab
                ? "bg-transparent text-white border-accent"
                : "text-muted border-transparent hover:text-white"
            }`}
          >
            {tab === "orders" ? "주문내역" : "체결내용"}
            <span className="ml-2 tabular-nums opacity-70">
              {tab === "orders" ? ordersTotal : fillsTotal}
            </span>
          </button>
        ))}
      </div>

      {/* 에러 메시지 */}
      {((mainTab === "orders" && (ordersError || actionError)) ||
        (mainTab === "fills" && fillsError)) && (
        <p className="px-4 py-2 text-negative text-xs font-sans border-b border-border bg-negative/5">
          {mainTab === "orders" ? ordersError || actionError : fillsError}
        </p>
      )}

      <div
        id={`${tabPanelId}-main-panel`}
        role="tabpanel"
        aria-labelledby={`${tabPanelId}-main-tab-${mainTab}`}
        className="flex flex-col"
      >
        {/* Orders 탭 콘텐츠 */}
        {mainTab === "orders" && (
          <>
            <div
              role="tablist"
              aria-label="주문 상태 필터"
              className="flex gap-1 px-4 pt-3 border-b border-border"
            >
              {(["pending", "completed", "conditional"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  id={`${tabPanelId}-order-tab-${t}`}
                  aria-selected={orderTab === t}
                  aria-controls={`${tabPanelId}-order-panel`}
                  onClick={() => setOrderTab(t)}
                  className={`px-2.5 py-1 text-xs font-sans rounded border transition-colors ${
                    orderTab === t
                      ? "bg-accent/20 text-accent border-accent/40"
                      : "text-muted border-border hover:text-white"
                  }`}
                >
                  {ORDER_TAB_LABEL[t]}
                  <span className="ml-1 tabular-nums opacity-70">
                    {orderCounts[t]}
                  </span>
                </button>
              ))}
            </div>

            <div
              id={`${tabPanelId}-order-panel`}
              role="tabpanel"
              aria-labelledby={`${tabPanelId}-order-tab-${orderTab}`}
              className="max-h-[500px] overflow-y-auto"
            >
              {visibleOrders.length === 0 ? (
                <p className="px-4 py-6 text-muted text-sm font-sans text-center">
                  {orderEmptyMessage}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm font-sans">
                    <thead className="sticky top-0 bg-surface">
                      <tr className="text-muted text-xs border-b border-border">
                        <th className="px-4 py-2 text-left">종목</th>
                        <th className="px-4 py-2 text-left">방향</th>
                        <th className="px-4 py-2 text-right">수량</th>
                        <th className="px-4 py-2 text-right">가격</th>
                        <th className="px-4 py-2 text-left">상태</th>
                        <th className="px-4 py-2 text-left">시각</th>
                        <th className="px-4 py-2 text-center">작업</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleOrders.map((o) => {
                        const brokerId = o.broker_order_id;
                        const canCancel =
                          CANCELLABLE_STATUSES.has(o.status) &&
                          brokerId != null;
                        const isLoading = loading === brokerId;
                        const isBuy = o.side === "BUY";

                        return (
                          <tr
                            key={o.client_order_id}
                            className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                          >
                            <td className="px-4 py-2">
                              <StockCell symbol={o.symbol} names={stockNames} />
                            </td>
                            <td
                              className={`px-4 py-2 font-semibold ${isBuy ? "text-positive" : "text-negative"}`}
                            >
                              {o.side}
                            </td>
                            <td className="px-4 py-2 text-right text-white tabular-nums">
                              {o.qty.toLocaleString()}
                            </td>
                            <td className="px-4 py-2 text-right text-white tabular-nums">
                              {o.price.toLocaleString("ko-KR")}
                            </td>
                            <td
                              className={`px-4 py-2 uppercase text-xs font-semibold ${STATUS_COLOR[o.status] ?? "text-muted"}`}
                            >
                              {o.status}
                            </td>
                            <td className={TIMESTAMP_CELL_CLASS}>
                              {o.created_at}
                            </td>
                            <td className="px-4 py-2 text-center">
                              {canCancel && brokerId && (
                                <button
                                  type="button"
                                  disabled={isLoading}
                                  onClick={() => handleCancel(brokerId)}
                                  className="text-xs px-2 py-1 rounded border border-negative/50 text-negative hover:bg-negative/10 disabled:opacity-40 transition-colors font-sans"
                                >
                                  {isLoading ? "취소중…" : "취소"}
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {/* Fills 탭 콘텐츠 */}
        {mainTab === "fills" && (
          <div className="max-h-[500px] overflow-y-auto">
            {fills.length === 0 ? (
              <p className="px-4 py-6 text-muted text-sm font-sans text-center">
                체결 내역 없음
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm font-sans">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="text-muted text-xs border-b border-border">
                      <th className="px-4 py-2 text-left">종목</th>
                      <th className="px-4 py-2 text-left">방향</th>
                      <th className="px-4 py-2 text-right">체결가</th>
                      <th className="px-4 py-2 text-right">수량</th>
                      <th className="px-4 py-2 text-left">통화</th>
                      <th className="px-4 py-2 text-left">시각</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fills.map((f, i) => (
                      <tr
                        key={`${f.symbol}-${f.timestamp}-${i}`}
                        className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                      >
                        <td className="px-4 py-2">
                          <StockCell symbol={f.symbol} names={stockNames} />
                        </td>
                        <td
                          className={`px-4 py-2 font-semibold ${
                            f.side === "BUY"
                              ? "text-positive"
                              : f.side === "SELL"
                                ? "text-negative"
                                : "text-muted"
                          }`}
                        >
                          {f.side ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-right text-white tabular-nums">
                          {f.price.toLocaleString("ko-KR")}
                        </td>
                        <td className="px-4 py-2 text-right text-white tabular-nums">
                          {f.volume.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-muted text-xs">
                          {f.currency}
                        </td>
                        <td className={TIMESTAMP_CELL_CLASS}>
                          {new Date(f.timestamp).toLocaleTimeString("ko-KR")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
