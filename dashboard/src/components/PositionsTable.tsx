import { fmtPrice } from "../lib/format";
import type { PositionItem } from "../api/types";

interface Props {
  positions: PositionItem[];
  error?: string | null;
}

/** Panel 안에 들어가는 본문만 렌더링 — 헤더/카운트는 상위 Panel이 담당 */
export function PositionsTable({ positions, error }: Props) {
  return (
    <>
      {error && (
        <p className="px-4 py-2 text-negative text-xs font-mono border-b border-border bg-negative/5">
          {error}
        </p>
      )}

      {positions.length === 0 ? (
        <p className="px-4 py-6 text-muted text-sm font-mono text-center">
          보유 포지션 없음
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="px-4 py-2 text-left">종목</th>
                <th className="px-4 py-2 text-right">수량</th>
                <th className="px-4 py-2 text-right">평균단가</th>
                <th className="px-4 py-2 text-right">장부금액</th>
                <th className="px-4 py-2 text-left">시장</th>
                <th className="px-4 py-2 text-left">진입시각</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr
                  key={`${p.symbol}-${p.env}`}
                  className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                >
                  <td className="px-4 py-2 text-white font-semibold">
                    {p.symbol}
                  </td>
                  <td className="px-4 py-2 text-right text-white">
                    {p.qty.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right text-white">
                    {fmtPrice(p.avg_price, p.market)}
                  </td>
                  <td className="px-4 py-2 text-right text-accent">
                    {fmtPrice(p.book_value, p.market)}
                  </td>
                  <td className="px-4 py-2 text-muted">{p.market}</td>
                  <td className="px-4 py-2 text-muted text-xs">
                    {p.opened_at}
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
