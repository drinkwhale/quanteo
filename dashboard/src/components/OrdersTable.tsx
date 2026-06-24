import type { OrderItem } from "../api/types";

const STATUS_COLOR: Record<string, string> = {
  pending: "text-warning",
  open: "text-accent",
  filled: "text-positive",
  cancelled: "text-muted",
  rejected: "text-negative",
};

interface Props {
  orders: OrderItem[];
  total: number;
}

export function OrdersTable({ orders, total }: Props) {
  return (
    <section className="bg-panel border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-white font-mono tracking-wider">
          주문내역
        </h2>
        <span className="text-xs text-muted font-mono">{total}건</span>
      </div>

      {orders.length === 0 ? (
        <p className="px-4 py-6 text-muted text-sm font-mono text-center">
          주문 내역 없음
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="px-4 py-2 text-left">종목</th>
                <th className="px-4 py-2 text-left">방향</th>
                <th className="px-4 py-2 text-right">수량</th>
                <th className="px-4 py-2 text-right">가격</th>
                <th className="px-4 py-2 text-left">상태</th>
                <th className="px-4 py-2 text-left">시각</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr
                  key={o.client_order_id}
                  className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                >
                  <td className="px-4 py-2 text-white font-semibold">
                    {o.symbol}
                  </td>
                  <td
                    className={`px-4 py-2 font-semibold ${o.side === "buy" ? "text-positive" : "text-negative"}`}
                  >
                    {o.side === "buy" ? "BUY" : "SELL"}
                  </td>
                  <td className="px-4 py-2 text-right text-white">
                    {o.qty.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right text-white">
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
