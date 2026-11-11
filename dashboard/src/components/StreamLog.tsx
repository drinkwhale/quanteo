import type { LogEntry } from "../hooks/useStream";
import { fmtClock, SIDE_LABEL, stockLabel } from "../lib/format";
import { cn } from "../lib/utils";
import { Panel } from "./Panel";

/** 이벤트 종류별 색 — 봇 상태 축만 쓴다. 매수/매도 방향은 본문에서 시세 색으로 따로 표시. */
const EVENT_TONE: readonly (readonly [string, string])[] = [
  ["error", "text-danger"],
  ["risk", "text-danger"],
  ["fill", "text-live"],
  ["order", "text-warn"],
  ["signal", "text-ink"],
];

function toneFor(eventType: string): string {
  const key = eventType.toLowerCase();
  return EVENT_TONE.find(([k]) => key.includes(k))?.[1] ?? "text-muted";
}

/** 시그널·주문처럼 방향·종목·가격이 있는 payload는 읽을 수 있는 한 줄로, 나머지는 JSON 그대로. */
function Payload({
  payload,
  names,
}: {
  payload: unknown;
  names: Map<string, string>;
}) {
  if (typeof payload !== "object" || payload === null) {
    return <>{String(payload ?? "")}</>;
  }
  const p = payload as Record<string, unknown>;
  if ((p.side === "BUY" || p.side === "SELL") && typeof p.symbol === "string") {
    return (
      <>
        <span
          className={cn(
            "font-semibold",
            p.side === "BUY" ? "text-up" : "text-down",
          )}
        >
          {SIDE_LABEL[p.side]}
        </span>{" "}
        <span className="text-ink">{stockLabel(p.symbol, names)}</span>
        {typeof p.price === "number" && ` @ ${p.price.toLocaleString()}`}
        {typeof p.reason === "string" && p.reason && ` · ${p.reason}`}
      </>
    );
  }
  return <>{JSON.stringify(payload)}</>;
}

interface Props {
  logs: LogEntry[];
  connected: boolean;
  stockNames: Map<string, string>;
  /** 오늘 Risk Manager를 통과한 주문 수 — 조회 실패 시 null */
  dailyOrderCount?: number | null;
  className?: string;
}

/** 봇 활동 — WebSocket 스트림으로 들어오는 시그널·주문·체결·리스크 이벤트 실시간 로그. */
export function StreamLog({
  logs,
  connected,
  stockNames,
  dailyOrderCount,
  className,
}: Props) {
  return (
    <Panel
      title="봇 활동"
      meta={
        dailyOrderCount != null ? `오늘 주문 ${dailyOrderCount}건` : undefined
      }
      className={className}
      actions={
        <span
          className={cn(
            "flex items-center gap-1.5 text-xs",
            connected ? "text-dim" : "font-semibold text-danger",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              connected ? "animate-pulse bg-live" : "bg-danger",
            )}
          />
          {connected ? "실시간" : "재연결 중…"}
        </span>
      }
    >
      {logs.length === 0 ? (
        <p className="state-msg">
          {connected
            ? "아직 이벤트가 없습니다. 봇이 시그널·주문·체결을 내면 여기에 실시간으로 쌓입니다."
            : "스트림 연결이 끊겨 이벤트를 받지 못하고 있습니다. 3초마다 재연결을 시도합니다."}
        </p>
      ) : (
        <ol className="divide-y divide-line/60 text-xs">
          {logs.map((log) => (
            <li
              key={log._key}
              className="grid grid-cols-[4.5rem_6.5rem_minmax(0,1fr)] items-baseline gap-2 px-4 py-1.5 hover:bg-raised/60"
            >
              <time className="num font-mono text-muted">
                {fmtClock(log.timestamp)}
              </time>
              <span
                className={cn(
                  "truncate font-mono font-semibold",
                  toneFor(log.event_type),
                )}
              >
                {log.event_type}
              </span>
              <span className="truncate text-dim">
                <Payload payload={log.payload} names={stockNames} />
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
