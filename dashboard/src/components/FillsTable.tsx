import type { FillItem } from "../api/types";

interface Props {
  fills: FillItem[];
  total: number;
  error?: string | null;
}

export function FillsTable({ fills, total, error }: Props) {
  return (
    <section className="bg-panel border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-white font-mono tracking-wider">
          체결내역
        </h2>
        <span className="text-xs text-muted font-mono">{total}건</span>
      </div>

      {error && (
        <p className="px-4 py-2 text-negative text-xs font-mono border-b border-border bg-negative/5">
          {error}
        </p>
      )}

      {fills.length === 0 ? (
        <p className="px-4 py-6 text-muted text-sm font-mono text-center">
          체결 내역 없음
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-mono">
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
                  <td className="px-4 py-2 text-white font-semibold">
                    {f.symbol}
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
                  <td className="px-4 py-2 text-right text-white">
                    {f.price.toLocaleString("ko-KR")}
                  </td>
                  <td className="px-4 py-2 text-right text-white">
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
    </section>
  );
}
