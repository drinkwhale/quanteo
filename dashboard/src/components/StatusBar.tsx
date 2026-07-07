import type { BotStatus } from "../api/types";

const HALT_COLOR: Record<string, string> = {
  none: "text-positive",
  reduce: "text-warning",
  pause: "text-warning",
  kill: "text-negative",
};

const HALT_LABEL: Record<string, string> = {
  none: "RUNNING",
  reduce: "REDUCE",
  pause: "PAUSED",
  kill: "KILL",
};

function fmtUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}h ${m}m ${s}s`;
}

interface Props {
  status: BotStatus | null;
  streamConnected: boolean;
}

export function StatusBar({ status, streamConnected }: Props) {
  if (!status) {
    return (
      <div className="sticky top-0 z-[var(--z-sticky)] flex items-center gap-3 px-4 py-2 bg-panel border-b border-border text-muted text-sm font-sans">
        <span className="animate-pulse">연결 중...</span>
      </div>
    );
  }

  const haltColor = HALT_COLOR[status.halt_level] ?? "text-muted";
  const haltLabel =
    HALT_LABEL[status.halt_level] ?? status.halt_level.toUpperCase();

  return (
    <div className="sticky top-0 z-[var(--z-sticky)] flex flex-wrap items-center gap-x-4 gap-y-1 sm:gap-x-6 px-4 py-2 bg-panel border-b border-border text-sm font-sans">
      <span className="font-semibold text-white tracking-wider whitespace-nowrap">
        quanteo
      </span>

      <span className={`font-semibold whitespace-nowrap ${haltColor}`}>
        {haltLabel}
      </span>

      <span className="text-muted whitespace-nowrap">
        ENV:{" "}
        <span
          className={
            status.env === "prod" ? "text-negative font-bold" : "text-accent"
          }
        >
          {status.env.toUpperCase()}
        </span>
      </span>

      <span className="text-muted whitespace-nowrap hidden sm:inline">
        MARKET: <span className="text-white">{status.market}</span>
      </span>

      <span className="text-muted whitespace-nowrap hidden md:inline">
        UPTIME:{" "}
        <span className="text-white tabular-nums">
          {fmtUptime(status.uptime_seconds)}
        </span>
      </span>

      <span className="ml-auto flex-shrink-0 flex items-center gap-1.5 text-muted whitespace-nowrap">
        <span
          className={`inline-block w-2 h-2 rounded-full ${streamConnected ? "bg-positive" : "bg-negative"}`}
        />
        {streamConnected ? "STREAM ON" : "STREAM OFF"}
      </span>
    </div>
  );
}
