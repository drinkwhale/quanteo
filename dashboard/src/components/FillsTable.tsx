import type { FillItem } from "../api/types";
import { StockCell } from "./StockCell";

interface Props {
  fills: FillItem[];
  error?: string | null;
  stockNames: Map<string, string>;
}

/** Panel 안에 들어가는 본문만 렌더링 — 헤더/카운트는 상위 Panel이 담당 */
export function FillsTable({ fills, error, stockNames }: Props) {
  return (
    <>
      {error && (
        <p className="px-4 py-2 text-negative text-xs font-sans border-b border-border bg-negative/5">
          {error}
        </p>
      )}

      {fills.length === 0 ? (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          체결 내역 없음
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans">
            <thead>
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
                  <td className="px-4 py-2 text-muted text-xs">{f.currency}</td>
                  <td className="px-4 py-2 text-muted text-xs">
                    {new Date(f.timestamp).toLocaleTimeString("ko-KR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
