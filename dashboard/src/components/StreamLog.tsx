import type { LogEntry } from "../hooks/useStream";

const EVENT_COLOR: Record<string, string> = {
  connected: "text-positive",
  signal: "text-accent",
  order: "text-warning",
  fill: "text-positive",
  risk: "text-negative",
  error: "text-negative",
  status: "text-muted",
};

function colorFor(eventType: string): string {
  for (const [key, color] of Object.entries(EVENT_COLOR)) {
    if (eventType.toLowerCase().includes(key)) return color;
  }
  return "text-muted";
}

interface Props {
  logs: LogEntry[];
}

/** Panel 안에 들어가는 본문만 렌더링 — 헤더/연결상태 배지는 상위 Panel(headerExtra)이 담당 */
export function StreamLog({ logs }: Props) {
  return (
    <div className="overflow-y-auto max-h-80 p-2 space-y-0.5">
      {logs.length === 0 ? (
        <p className="px-2 py-4 text-muted text-xs font-sans text-center">
          이벤트 대기 중...
        </p>
      ) : (
        logs.map((log) => (
          <div
            key={log._key}
            className="flex gap-3 px-2 py-0.5 hover:bg-surface rounded text-xs font-sans"
          >
            <span className="text-muted flex-shrink-0 w-20 truncate">
              {new Date(log.timestamp).toLocaleTimeString("ko-KR")}
            </span>
            <span
              className={`flex-shrink-0 w-28 truncate font-semibold ${colorFor(log.event_type)}`}
            >
              {log.event_type}
            </span>
            <span className="text-muted truncate">
              {typeof log.payload === "object"
                ? JSON.stringify(log.payload)
                : String(log.payload)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

/** StreamLog Panel 헤더에 붙는 연결상태 배지 (headerExtra로 전달) */
export function StreamConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-xs font-sans text-muted">
      <span
        className={`inline-block w-2 h-2 rounded-full ${connected ? "bg-positive animate-pulse" : "bg-negative"}`}
      />
      {connected ? "연결됨" : "재연결 중..."}
    </span>
  );
}
