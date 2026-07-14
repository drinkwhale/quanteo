import { useId, useMemo, useState } from "react";
import { api } from "../api/client";
import type { OrderItem, OrderStatus } from "../api/types";
import { StockCell } from "./StockCell";

const STATUS_COLOR: Record<OrderStatus, string> = {
  pending: "text-warning",
  submitted: "text-accent",
  partial: "text-accent",
  filled: "text-positive",
  cancelled: "text-muted",
  rejected: "text-negative",
};

// partial(부분체결)도 취소 가능 — Toss는 PARTIAL_FILLED를 PENDING과 같은
// OPEN 그룹으로 취급하고(core/execution/order_sync.py), cancel_order API도
// 상태로 막지 않고 그대로 브로커에 전달한다.
const CANCELLABLE_STATUSES: ReadonlySet<OrderStatus> = new Set([
  "pending",
  "submitted",
  "partial",
]);

type OrderTab = "pending" | "completed";

// 대기 = 아직 종결되지 않은 주문, 완료 = 종결된 주문(체결/취소/거부 모두 포함).
// Record<OrderStatus, OrderTab>이라 OrderStatus에 값이 추가되는데 여기 안
// 채우면 컴파일 에러가 난다 — 새 상태가 조용히 안 보이게 되는 걸 막는다.
const STATUS_TAB: Record<OrderStatus, OrderTab> = {
  pending: "pending",
  submitted: "pending",
  partial: "pending",
  filled: "completed",
  cancelled: "completed",
  rejected: "completed",
};

type VisibleTab = OrderTab | "conditional";

const TAB_LABEL: Record<VisibleTab, string> = {
  pending: "대기",
  completed: "완료",
  conditional: "조건주문",
};

interface Props {
  orders: OrderItem[];
  error?: string | null;
  onRefetch?: () => void;
  stockNames: Map<string, string>;
}

/** Panel 안에 들어가는 본문만 렌더링 — 헤더/카운트는 상위 Panel이 담당 */
export function OrdersTable({ orders, error, onRefetch, stockNames }: Props) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null); // order_id being actioned
  const [tab, setTab] = useState<VisibleTab>("pending");
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

  // 한 번의 순회로 대기/완료를 나눈다 — status가 STATUS_TAB에 없는(백엔드가
  // 새 상태를 추가했거나 데이터가 오염된) 주문은 두 탭 어디에도 안 들어가고
  // 조용히 사라지는 대신 콘솔에 경고를 남긴다. 트레이딩 대시보드에서 주문이
  // 아무 표시 없이 안 보이는 건 위험하기 때문.
  const grouped = useMemo(() => {
    const result: Record<OrderTab, OrderItem[]> = {
      pending: [],
      completed: [],
    };
    for (const o of orders) {
      const t = STATUS_TAB[o.status];
      if (t === undefined) {
        console.warn(
          `[OrdersTable] 알 수 없는 주문 상태 — 목록에 표시되지 않습니다: status=${o.status} client_order_id=${o.client_order_id}`,
        );
        continue;
      }
      result[t].push(o);
    }
    return result;
  }, [orders]);

  const counts = useMemo(
    () => ({
      pending: grouped.pending.length,
      completed: grouped.completed.length,
      // Toss 어댑터는 LIMIT/MARKET만 지원 — 조건주문 데이터가 없어 항상 0건.
      conditional: 0,
    }),
    [grouped],
  );

  const visibleOrders = tab === "conditional" ? [] : grouped[tab];

  const emptyMessage =
    tab === "conditional"
      ? "조건주문 기능은 아직 지원되지 않음"
      : "주문 내역 없음";

  return (
    <>
      {(error || actionError) && (
        <p className="px-4 py-2 text-negative text-xs font-sans border-b border-border bg-negative/5">
          {error ?? actionError}
        </p>
      )}

      <div
        role="tablist"
        aria-label="주문 상태 필터"
        className="flex gap-1 px-4 pt-3"
      >
        {(["pending", "completed", "conditional"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            id={`${tabPanelId}-tab-${t}`}
            aria-selected={tab === t}
            aria-controls={`${tabPanelId}-panel`}
            onClick={() => setTab(t)}
            className={`px-2.5 py-1 text-xs font-sans rounded border transition-colors ${
              tab === t
                ? "bg-accent/20 text-accent border-accent/40"
                : "text-muted border-border hover:text-white"
            }`}
          >
            {TAB_LABEL[t]}
            <span className="ml-1 tabular-nums opacity-70">{counts[t]}</span>
          </button>
        ))}
      </div>

      <div
        id={`${tabPanelId}-panel`}
        role="tabpanel"
        aria-labelledby={`${tabPanelId}-tab-${tab}`}
      >
        {visibleOrders.length === 0 ? (
          <p className="px-4 py-6 text-muted text-sm font-sans text-center">
            {emptyMessage}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans">
              <thead>
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
                    CANCELLABLE_STATUSES.has(o.status) && brokerId != null;
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
                      <td className="px-4 py-2 text-muted text-xs font-mono">
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
  );
}
