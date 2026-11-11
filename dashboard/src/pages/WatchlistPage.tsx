import { RotateCw } from "lucide-react";
import { Panel } from "../components/Panel";
import { useWatchlist } from "../hooks/useWatchlist";
import { fmtStamp } from "../lib/format";

/**
 * score_snapshot은 등록 시점 스코어 축 구성이 고정돼 있지 않아(analyst_agent의
 * score_breakdown 축이 바뀔 수 있음) 특정 키를 하드코딩하지 않고 있는 그대로
 * 나열한다.
 */
function ScoreSnapshot({ snapshot }: { snapshot: Record<string, number> }) {
  const entries = Object.entries(snapshot);
  if (entries.length === 0) return <span className="text-muted">—</span>;
  return (
    <span className="text-xs text-dim">
      {entries.map(([key, value]) => `${key} ${value}`).join(" · ")}
    </span>
  );
}

export function WatchlistPage() {
  const { watchlist, error, isLoading, refetch } = useWatchlist();
  const items = watchlist?.items ?? [];

  return (
    <Panel
      title="관심종목"
      meta={watchlist ? `${items.length}건` : undefined}
      className="lg:h-full"
      actions={
        <button
          type="button"
          onClick={refetch}
          className="btn btn-icon h-7 w-7"
          title="새로고침"
          aria-label="관심종목 새로고침"
        >
          <RotateCw aria-hidden="true" className="h-3.5 w-3.5" />
        </button>
      }
    >
      {error && <p className="state-err">{error}</p>}

      {isLoading && <p className="state-msg">관심종목 불러오는 중…</p>}

      {!isLoading && !error && items.length === 0 && (
        <p className="state-msg">
          아직 등록된 관심종목이 없습니다.
          <br />
          Telegram 일일 추천 리포트에서 &quot;워치리스트 등록&quot; 버튼을
          누르면 여기 표시됩니다.
        </p>
      )}

      {!isLoading && items.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th scope="col">종목</th>
              <th scope="col">등록일</th>
              <th scope="col">출처</th>
              <th scope="col">등록 시점 스코어</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.symbol}>
                <td>
                  <span className="font-semibold text-ink">{item.name}</span>
                  <span className="ml-2 font-mono text-2xs text-muted">
                    {item.symbol}
                  </span>
                </td>
                <td className="font-mono text-xs text-muted">
                  {fmtStamp(item.added_at)}
                </td>
                <td className="text-dim">{item.source}</td>
                <td>
                  <ScoreSnapshot snapshot={item.score_snapshot} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
