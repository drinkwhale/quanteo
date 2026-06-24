import type { PositionItem } from "../api/types";

function fmtKRW(n: number): string {
  return n.toLocaleString("ko-KR") + "원";
}

interface Props {
  positions: PositionItem[];
  total: number;
}

export function PositionsTable({ positions, total }: Props) {
  return (
    <section className="bg-panel border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-white font-mono tracking-wider">
          포지션
        </h2>
        <span className="text-xs text-muted font-mono">{total}건</span>
      </div>

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
                    {fmtKRW(p.avg_price)}
                  </td>
                  <td className="px-4 py-2 text-right text-accent">
                    {fmtKRW(p.book_value)}
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
    </section>
  );
}
