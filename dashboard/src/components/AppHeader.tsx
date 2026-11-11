import type { BotStatus, MarketDayStatus } from "../api/types";
import { fmtUptime } from "../lib/format";
import { cn } from "../lib/utils";
import { VIEWS, type ViewId } from "../lib/views";
import { BotControls } from "./BotControls";

interface Props {
  view: ViewId;
  status: BotStatus | null;
  markets: MarketDayStatus[];
  streamConnected: boolean;
  onAction: () => void;
}

/**
 * 어느 화면에서든 고정되는 관제 바 — 왼쪽은 "어디를 볼지", 오른쪽은 "봇이 어떤 상태이고 어떻게 멈출지".
 * 화면 전환은 해시 링크라 뒤로가기·북마크가 그대로 동작한다.
 */
export function AppHeader({
  view,
  status,
  markets,
  streamConnected,
  onAction,
}: Props) {
  const isProd = status?.env === "prod";

  return (
    <header className="sticky top-0 z-[var(--z-sticky)] border-b border-line bg-panel">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2">
        <span className="text-[15px] font-bold tracking-tight text-ink">
          quanteo
        </span>

        <nav aria-label="화면 전환" className="flex items-center gap-0.5">
          {VIEWS.map((v) => {
            const isCurrent = v.id === view;
            return (
              <a
                key={v.id}
                href={`#${v.id}`}
                aria-current={isCurrent ? "page" : undefined}
                className={cn(
                  "flex h-8 items-center whitespace-nowrap rounded-md px-3 text-data font-medium transition-colors duration-150",
                  isCurrent
                    ? "bg-raised text-ink"
                    : "text-muted hover:bg-raised/60 hover:text-ink",
                )}
              >
                {v.label}
              </a>
            );
          })}
        </nav>

        <dl className="num ml-auto hidden items-center gap-x-4 text-xs xl:flex">
          {markets.map((m) => (
            <div key={m.market} className="flex items-center gap-1.5">
              <dt className="text-muted">{m.market}</dt>
              <dd
                className={m.is_open ? "font-semibold text-ink" : "text-muted"}
              >
                {m.is_open ? "장중" : "휴장"}
              </dd>
            </div>
          ))}
          {status && (
            <div className="flex items-center gap-1.5">
              <dt className="text-muted">가동</dt>
              <dd className="text-dim">{fmtUptime(status.uptime_seconds)}</dd>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <dt className="text-muted">스트림</dt>
            <dd
              className={cn(
                "flex items-center gap-1.5",
                streamConnected ? "text-dim" : "font-semibold text-danger",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  streamConnected ? "bg-live" : "bg-danger",
                )}
              />
              {streamConnected ? "연결됨" : "끊김"}
            </dd>
          </div>
        </dl>

        <div className="flex items-center gap-3 max-xl:ml-auto">
          {status && (
            <span
              title={
                isProd
                  ? "실전투자 환경 — 주문이 실제 계좌에 반영됩니다"
                  : "모의투자 환경"
              }
              className={cn(
                "inline-flex h-6 items-center whitespace-nowrap rounded border px-2 text-2xs font-bold",
                isProd
                  ? "border-danger/60 text-danger"
                  : "border-line-strong text-dim",
              )}
            >
              {isProd ? "실전" : "모의"}
            </span>
          )}
          <BotControls status={status} onAction={onAction} />
        </div>
      </div>
    </header>
  );
}
