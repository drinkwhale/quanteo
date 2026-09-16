import { RotateCw } from "lucide-react";
import { Panel } from "../components/Panel";
import { useWatchlist } from "../hooks/useWatchlist";
import { fmtMarketCapBillion, pnlColorClass } from "../lib/format";

function GrowthCell({ pct }: { pct: number }) {
  const sign = pct > 0 ? "+" : "";
  return (
    <td
      className={`px-4 py-2 text-right font-semibold tabular-nums ${pnlColorClass(pct)}`}
    >
      {sign}
      {pct.toFixed(2)}%
    </td>
  );
}

export function WatchlistPage() {
  const { watchlist, error, notFound, isLoading, refetch } = useWatchlist();

  return (
    <Panel
      title="관심종목"
      badge={watchlist ? `${watchlist.date} 기준` : undefined}
      headerExtra={
        <button
          type="button"
          onClick={refetch}
          className="p-1.5 rounded hover:bg-accent/10 transition-colors"
          title="새로고침"
          aria-label="관심종목 새로고침"
        >
          <RotateCw className="w-4 h-4 text-muted hover:text-accent" />
        </button>
      }
    >
      {error && (
        <p className="px-4 py-2 text-negative text-xs font-sans border-b border-border bg-negative/5">
          {error}
        </p>
      )}

      {isLoading && (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          불러오는 중...
        </p>
      )}

      {!isLoading && notFound && (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          아직 생성된 관심종목이 없습니다. Stock Miner가 매일 실행되면 여기에
          결과가 표시됩니다.
        </p>
      )}

      {!isLoading && watchlist && watchlist.items.length === 0 && (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          조건을 충족한 종목이 없습니다.
        </p>
      )}

      {!isLoading && watchlist && watchlist.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="px-4 py-2 text-left">종목</th>
                <th className="px-4 py-2 text-right">시가총액</th>
                <th className="px-4 py-2 text-right">자산증가율</th>
                <th className="px-4 py-2 text-right">영업이익증가율</th>
                <th className="px-4 py-2 text-right">매출증가율</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.items.map((item) => (
                <tr
                  key={item.ticker}
                  className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                >
                  <td className="px-4 py-2 font-medium">
                    {item.name}
                    <span className="ml-1.5 text-xs text-muted">
                      {item.ticker}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-white tabular-nums">
                    {fmtMarketCapBillion(item.market_cap_billion)}
                  </td>
                  <GrowthCell pct={item.asset_growth_pct} />
                  <GrowthCell pct={item.oi_growth_pct} />
                  <GrowthCell pct={item.revenue_growth_pct} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
