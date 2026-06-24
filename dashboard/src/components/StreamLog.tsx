import type { StreamMessage } from "../api/types";

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
  logs: StreamMessage[];
  connected: boolean;
}

export function StreamLog({ logs, connected }: Props) {
  return (
    <section className="bg-panel border border-border rounded-lg overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <h2 className="text-sm font-semibold text-white font-mono tracking-wider">
          실시간 이벤트
        </h2>
        <span className="flex items-center gap-1.5 text-xs font-mono text-muted">
          <span
            className={`inline-block w-2 h-2 rounded-full ${connected ? "bg-positive animate-pulse" : "bg-negative"}`}
          />
          {connected ? "연결됨" : "재연결 중..."}
        </span>
      </div>

      <div className="overflow-y-auto max-h-80 p-2 space-y-0.5">
        {logs.length === 0 ? (
          <p className="px-2 py-4 text-muted text-xs font-mono text-center">
            이벤트 대기 중...
          </p>
        ) : (
          logs.map((log, i) => (
            <div
              key={i}
              className="flex gap-3 px-2 py-0.5 hover:bg-surface rounded text-xs font-mono"
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
    </section>
  );
}
