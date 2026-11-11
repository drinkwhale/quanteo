import { useEffect, useMemo, useRef, useState } from "react";
import type { LogEntry } from "../hooks/useStream";
import { SIDE_LABEL, stockLabel } from "../lib/format";
import { cn } from "../lib/utils";

interface SignalToast {
  id: number;
  side: "BUY" | "SELL";
  symbol: string;
  price: number;
  reason: string;
}

const TOAST_TTL_MS = 8_000;
const MAX_TOASTS = 5;

/** 스트림 payload는 외부 입력이라 캐스트하지 않고 런타임에 모양을 확인한다. */
function toToast(log: LogEntry): SignalToast | null {
  if (log.event_type !== "signal") return null;
  const p = log.payload as Record<string, unknown> | null;
  if (!p || typeof p.symbol !== "string") return null;
  if (p.side !== "BUY" && p.side !== "SELL") return null;
  return {
    id: log._key,
    side: p.side,
    symbol: p.symbol,
    price: typeof p.price === "number" ? p.price : 0,
    reason: typeof p.reason === "string" ? p.reason : "",
  };
}

interface Props {
  logs: LogEntry[];
  stockNames: Map<string, string>;
}

/**
 * 스트림의 signal 이벤트를 화면 우상단 토스트로 띄운다.
 * 앱 최상위에 한 번만 두기 때문에 어느 화면을 보고 있든 시그널을 놓치지 않는다.
 * 토스트 목록은 logs에서 파생하고, 상태로는 "만료된 id"만 들고 있는다.
 */
export function SignalToaster({ logs, stockNames }: Props) {
  const [expired, setExpired] = useState<ReadonlySet<number>>(new Set());
  const timersRef = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const signals = useMemo(
    () =>
      logs
        .map(toToast)
        .filter((t): t is SignalToast => t !== null)
        .slice(0, MAX_TOASTS),
    [logs],
  );

  useEffect(() => {
    const timers = timersRef.current;
    for (const { id } of signals) {
      if (timers.has(id)) continue;
      timers.set(
        id,
        setTimeout(
          () => setExpired((prev) => new Set(prev).add(id)),
          TOAST_TTL_MS,
        ),
      );
    }
  }, [signals]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  const toasts = signals.filter((t) => !expired.has(t.id));

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed right-4 top-16 z-[var(--z-toast)] flex w-72 flex-col gap-2"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className="animate-[rise-in_0.2s_var(--ease-out)] rounded-lg border border-line-strong bg-raised px-4 py-3 shadow-xl shadow-black/50"
        >
          <div
            className={cn(
              "text-sm font-bold",
              t.side === "BUY" ? "text-up" : "text-down",
            )}
          >
            {SIDE_LABEL[t.side]} 시그널
          </div>
          <div className="num mt-0.5 text-data text-ink">
            {stockLabel(t.symbol, stockNames)}
            {t.price > 0 && ` @ ${t.price.toLocaleString()}`}
          </div>
          {t.reason && (
            <div className="mt-0.5 truncate text-xs text-muted">{t.reason}</div>
          )}
        </div>
      ))}
    </div>
  );
}
