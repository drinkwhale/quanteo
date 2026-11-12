import { RotateCw } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { FillItem, OrderItem, OrderStatus } from "../api/types";
import {
  fmtPrice,
  fmtStamp,
  SIDE_LABEL,
  sideClass,
  stockLabel,
} from "../lib/format";
import { cn } from "../lib/utils";
import { Panel } from "./Panel";
import { Segmented } from "./Segmented";

type Tab = "open" | "done" | "fills";

/** 주문 상태 → 표시. 상태는 "주문이 어디까지 갔나"라 시세 색(빨강/파랑)을 쓰지 않는다. */
const STATUS_META: Record<
  OrderStatus,
  { label: string; tab: Exclude<Tab, "fills">; className: string }
> = {
  pending: { label: "대기", tab: "open", className: "text-warn" },
  submitted: { label: "접수", tab: "open", className: "text-ink" },
  partial: { label: "부분체결", tab: "open", className: "text-ink" },
  filled: { label: "체결", tab: "done", className: "text-live" },
  cancelled: { label: "취소", tab: "done", className: "text-muted" },
  rejected: { label: "거부", tab: "done", className: "text-danger" },
};

function StockName({
  symbol,
  names,
}: {
  symbol: string;
  names: Map<string, string>;
}) {
  const hasName = names.has(symbol);
  return (
    <>
      <div className="font-semibold text-ink">{stockLabel(symbol, names)}</div>
      {hasName && <div className="font-mono text-2xs text-muted">{symbol}</div>}
    </>
  );
}

interface Props {
  orders: OrderItem[];
  fills: FillItem[];
  ordersError?: string | null;
  fillsError?: string | null;
  fillsTotal: number;
  onRefetch?: () => void;
  stockNames: Map<string, string>;
  className?: string;
}

export function OrdersAndFillsPanel({
  orders,
  fills,
  ordersError,
  fillsError,
  fillsTotal,
  onRefetch,
  stockNames,
  className,
}: Props) {
  const [tab, setTab] = useState<Tab>("open");
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);

  async function handleCancel(orderId: string) {
    setCancelling(orderId);
    setActionError(null);
    try {
      await api.cancelOrder(orderId);
      onRefetch?.();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "취소 실패");
    } finally {
      setCancelling(null);
    }
  }

  const grouped = useMemo(() => {
    const result: Record<Exclude<Tab, "fills">, OrderItem[]> = {
      open: [],
      done: [],
    };
    for (const o of orders) {
      const meta = STATUS_META[o.status];
      if (meta === undefined) {
        console.warn(
          `[OrdersAndFillsPanel] 알 수 없는 주문 상태 — 목록에 표시되지 않습니다: status=${o.status} client_order_id=${o.client_order_id}`,
        );
        continue;
      }
      result[meta.tab].push(o);
    }
    return result;
  }, [orders]);

  const errorMessage =
    tab === "fills" ? fillsError : (actionError ?? ordersError);
  const visibleOrders = tab === "fills" ? [] : grouped[tab];

  return (
    <Panel
      title="주문·체결"
      className={className}
      actions={
        <>
          <Segmented
            label="주문·체결 구분"
            value={tab}
            onChange={setTab}
            options={[
              { value: "open", label: "미체결", count: grouped.open.length },
              { value: "done", label: "완료", count: grouped.done.length },
              { value: "fills", label: "체결내역", count: fillsTotal },
            ]}
          />
          <button
            type="button"
            onClick={onRefetch}
            className="btn btn-icon h-7 w-7"
            title="새로고침"
            aria-label="주문·체결 새로고침"
          >
            <RotateCw aria-hidden="true" className="h-3.5 w-3.5" />
          </button>
        </>
      }
    >
      {errorMessage && (
        <p className="state-err">
          {tab === "fills" ? "체결 조회 실패" : "주문 조회 실패"} —{" "}
          {errorMessage}
        </p>
      )}

      {tab !== "fills" &&
        (visibleOrders.length === 0 ? (
          // 조회가 실패했는데 "주문이 없습니다"라고 하면 거짓말이 된다 — 에러만 보여준다
          !errorMessage && (
            <p className="state-msg">
              {tab === "open"
                ? "미체결 주문이 없습니다. 봇이 낸 주문이 체결 대기 중이면 여기서 취소할 수 있습니다."
                : "완료된 주문이 없습니다."}
            </p>
          )
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th scope="col">종목</th>
                <th scope="col">구분</th>
                <th scope="col" className="r">
                  수량
                </th>
                <th scope="col" className="r">
                  주문가
                </th>
                <th scope="col">상태</th>
                <th scope="col">주문 시각</th>
                {tab === "open" && (
                  <th scope="col" className="r">
                    <span className="sr-only">작업</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {visibleOrders.map((o) => {
                const brokerId = o.broker_order_id;
                const status = STATUS_META[o.status];
                return (
                  <tr key={o.client_order_id}>
                    <td>
                      <StockName symbol={o.symbol} names={stockNames} />
                    </td>
                    <td className={cn("font-semibold", sideClass(o.side))}>
                      {SIDE_LABEL[o.side]}
                    </td>
                    <td className="r text-ink">{o.qty.toLocaleString()}</td>
                    <td className="r text-ink">
                      {fmtPrice(o.price, o.market)}
                    </td>
                    <td className={cn("font-medium", status.className)}>
                      {status.label}
                    </td>
                    <td className="font-mono text-xs text-muted">
                      {fmtStamp(o.created_at)}
                    </td>
                    {tab === "open" && (
                      <td className="r">
                        {brokerId != null && (
                          <button
                            type="button"
                            disabled={cancelling === brokerId}
                            onClick={() => handleCancel(brokerId)}
                            className="btn h-7 px-2.5"
                          >
                            {cancelling === brokerId ? "취소 중…" : "주문 취소"}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        ))}

      {tab === "fills" &&
        (fills.length === 0 ? (
          !errorMessage && <p className="state-msg">체결 내역이 없습니다.</p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th scope="col">종목</th>
                <th scope="col">구분</th>
                <th scope="col" className="r">
                  체결가
                </th>
                <th scope="col" className="r">
                  수량
                </th>
                <th scope="col">체결 시각</th>
              </tr>
            </thead>
            <tbody>
              {fills.map((f, i) => (
                <tr key={`${f.symbol}-${f.timestamp}-${i}`}>
                  <td>
                    <StockName symbol={f.symbol} names={stockNames} />
                  </td>
                  <td className={cn("font-semibold", sideClass(f.side))}>
                    {f.side ? SIDE_LABEL[f.side] : "—"}
                  </td>
                  <td className="r text-ink">
                    {fmtPrice(
                      f.price,
                      f.currency === "USD" ? "overseas" : "domestic",
                    )}
                  </td>
                  <td className="r text-ink">{f.volume.toLocaleString()}</td>
                  <td className="font-mono text-xs text-muted">
                    {fmtStamp(f.timestamp)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </Panel>
  );
}
