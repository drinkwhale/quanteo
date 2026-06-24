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
      <div className="flex items-center gap-3 px-4 py-2 bg-panel border-b border-border text-muted text-sm font-mono">
        <span className="animate-pulse">연결 중...</span>
      </div>
    );
  }

  const haltColor = HALT_COLOR[status.halt_level] ?? "text-muted";
  const haltLabel =
    HALT_LABEL[status.halt_level] ?? status.halt_level.toUpperCase();

  return (
    <div className="flex items-center gap-6 px-4 py-2 bg-panel border-b border-border text-sm font-mono">
      <span className="font-semibold text-white tracking-wider">quanteo</span>

      <span className={`font-semibold ${haltColor}`}>{haltLabel}</span>

      <span className="text-muted">
        ENV:{" "}
        <span
          className={
            status.env === "prod" ? "text-negative font-bold" : "text-accent"
          }
        >
          {status.env.toUpperCase()}
        </span>
      </span>

      <span className="text-muted">
        MARKET: <span className="text-white">{status.market}</span>
      </span>

      <span className="text-muted">
        UPTIME:{" "}
        <span className="text-white">{fmtUptime(status.uptime_seconds)}</span>
      </span>

      <span className="ml-auto flex items-center gap-1.5 text-muted">
        <span
          className={`inline-block w-2 h-2 rounded-full ${streamConnected ? "bg-positive" : "bg-negative"}`}
        />
        {streamConnected ? "STREAM ON" : "STREAM OFF"}
      </span>
    </div>
  );
}
