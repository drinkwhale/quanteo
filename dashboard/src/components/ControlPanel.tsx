import { useState } from "react";
import { api } from "../api/client";
import type { BotStatus } from "../api/types";

interface Props {
  status: BotStatus | null;
  onAction: () => void;
}

type Action = "pause" | "resume" | "kill";

const CONFIRM_MESSAGE: Record<Action, string> = {
  pause: "봇을 일시정지하겠습니까?",
  resume: "봇을 재개하겠습니까?",
  kill: "⚠️ 킬스위치를 활성화하면 모든 신규 주문이 차단됩니다. 계속하겠습니까?",
};

export function ControlPanel({ status, onAction }: Props) {
  const [loading, setLoading] = useState<Action | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(
    null,
  );

  const isPaused = status?.halt_level === "pause";
  const isKilled = status?.halt_level === "kill";

  async function execute(action: Action) {
    if (!window.confirm(CONFIRM_MESSAGE[action])) return;

    setLoading(action);
    setFeedback(null);
    try {
      const handlers: Record<
        Action,
        () => Promise<{ success: boolean; message: string }>
      > = {
        pause: api.pause,
        resume: api.resume,
        kill: api.kill,
      };
      const res = await handlers[action]();
      setFeedback({ ok: res.success, msg: res.message || "완료" });
      onAction();
    } catch (e: unknown) {
      setFeedback({
        ok: false,
        msg: e instanceof Error ? e.message : "오류 발생",
      });
    } finally {
      setLoading(null);
    }
  }

  return (
    <section className="bg-panel border border-border rounded-lg p-4 space-y-4">
      <h2 className="text-sm font-semibold text-white font-mono tracking-wider">
        봇 제어
      </h2>

      <div className="flex gap-3 flex-wrap">
        <button
          onClick={() => execute("pause")}
          disabled={isPaused || isKilled || loading !== null}
          className="px-4 py-2 rounded bg-warning/10 text-warning border border-warning/30 text-sm font-mono font-semibold
                     hover:bg-warning/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading === "pause" ? "처리 중..." : "일시정지"}
        </button>

        <button
          onClick={() => execute("resume")}
          disabled={(!isPaused && !isKilled) || loading !== null}
          className="px-4 py-2 rounded bg-positive/10 text-positive border border-positive/30 text-sm font-mono font-semibold
                     hover:bg-positive/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading === "resume" ? "처리 중..." : "재개"}
        </button>

        <button
          onClick={() => execute("kill")}
          disabled={isKilled || loading !== null}
          className="px-4 py-2 rounded bg-negative/10 text-negative border border-negative/30 text-sm font-mono font-semibold
                     hover:bg-negative/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors ml-auto"
        >
          {loading === "kill" ? "처리 중..." : "킬스위치"}
        </button>
      </div>

      {feedback && (
        <p
          className={`text-xs font-mono px-3 py-2 rounded border ${
            feedback.ok
              ? "text-positive bg-positive/5 border-positive/20"
              : "text-negative bg-negative/5 border-negative/20"
          }`}
        >
          {feedback.msg}
        </p>
      )}

      {status?.env === "prod" && (
        <p className="text-xs font-mono text-negative border border-negative/30 bg-negative/5 px-3 py-2 rounded">
          ⚠️ 실전투자 환경 — 주문이 실제 계좌에 영향을 미칩니다
        </p>
      )}
    </section>
  );
}
