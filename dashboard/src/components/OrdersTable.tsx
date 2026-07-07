import { useState } from "react";
import { api } from "../api/client";
import type { OrderItem } from "../api/types";
import { StockCell } from "./StockCell";

const STATUS_COLOR: Record<string, string> = {
  pending: "text-warning",
  open: "text-accent",
  submitted: "text-accent",
  filled: "text-positive",
  cancelled: "text-muted",
  rejected: "text-negative",
};

const CANCELLABLE_STATUSES = new Set(["pending", "submitted", "open"]);

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

  return (
    <>
      {(error || actionError) && (
        <p className="px-4 py-2 text-negative text-xs font-sans border-b border-border bg-negative/5">
          {error ?? actionError}
        </p>
      )}

      {orders.length === 0 ? (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          주문 내역 없음
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
              {orders.map((o) => {
                const brokerId = o.kis_order_id;
                const canCancel =
                  CANCELLABLE_STATUSES.has(o.status) && brokerId != null;
                const isLoading = loading === brokerId;

                return (
                  <tr
                    key={o.client_order_id}
                    className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                  >
                    <td className="px-4 py-2">
                      <StockCell symbol={o.symbol} names={stockNames} />
                    </td>
                    <td
                      className={`px-4 py-2 font-semibold ${o.side === "BUY" ? "text-positive" : "text-negative"}`}
                    >
                      {o.side === "BUY" ? "BUY" : "SELL"}
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
                    <td className="px-4 py-2 text-muted text-xs">
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
    </>
  );
}
