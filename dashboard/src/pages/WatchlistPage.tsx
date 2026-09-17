import { RotateCw } from "lucide-react";
import { Panel } from "../components/Panel";
import { useWatchlist } from "../hooks/useWatchlist";

/** ISO 문자열을 그대로 보여주면 가독성이 떨어져 로컬 표기로 변환한다 —
 * 파싱 실패 시(예상 밖 포맷) 원본 문자열을 그대로 보여준다. */
function formatAddedAt(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("ko-KR");
}

/**
 * score_snapshot은 등록 시점 스코어 축 구성이 고정돼 있지 않아(analyst_agent의
 * score_breakdown 축이 바뀔 수 있음) 특정 키를 하드코딩하지 않고 있는 그대로
 * 나열한다.
 */
function ScoreSnapshot({ snapshot }: { snapshot: Record<string, number> }) {
  const entries = Object.entries(snapshot);
  if (entries.length === 0) return <span className="text-muted">-</span>;
  return (
    <span className="text-xs text-muted">
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
      badge={watchlist ? `${items.length}건` : undefined}
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

      {!isLoading && !error && items.length === 0 && (
        <p className="px-4 py-6 text-muted text-sm font-sans text-center">
          아직 등록된 관심종목이 없습니다. Telegram 리포트에서 &quot;워치리스트
          등록&quot; 버튼을 누르면 여기 표시됩니다.
        </p>
      )}

      {!isLoading && items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="px-4 py-2 text-left">종목</th>
                <th className="px-4 py-2 text-left">등록일</th>
                <th className="px-4 py-2 text-left">출처</th>
                <th className="px-4 py-2 text-left">스코어</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.symbol}
                  className="border-b border-border last:border-0 hover:bg-surface transition-colors"
                >
                  <td className="px-4 py-2 font-medium">
                    {item.name}
                    <span className="ml-1.5 text-xs text-muted">
                      {item.symbol}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-muted tabular-nums">
                    {formatAddedAt(item.added_at)}
                  </td>
                  <td className="px-4 py-2 text-muted">{item.source}</td>
                  <td className="px-4 py-2">
                    <ScoreSnapshot snapshot={item.score_snapshot} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
