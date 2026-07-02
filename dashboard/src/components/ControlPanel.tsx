import { useState } from "react";
import { api } from "../api/client";
import type { BotStatus } from "../api/types";
import { ConfirmDialog } from "./ConfirmDialog";
import { KillSwitchButton } from "./KillSwitchButton";

interface Props {
  status: BotStatus | null;
  onAction: () => void;
}

type ToggleAction = "pause" | "resume";

const CONFIRM_MESSAGE: Record<ToggleAction, string> = {
  pause: "봇을 일시정지하겠습니까?",
  resume: "봇을 재개하겠습니까?",
};

export function ControlPanel({ status, onAction }: Props) {
  const [loading, setLoading] = useState<ToggleAction | null>(null);
  const [pending, setPending] = useState<ToggleAction | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(
    null,
  );

  const isPaused = status?.halt_level === "pause";
  const isKilled = status?.halt_level === "kill";

  async function execute(action: ToggleAction) {
    setPending(null);
    setLoading(action);
    setFeedback(null);
    try {
      const handlers: Record<
        ToggleAction,
        () => Promise<{ success: boolean; message: string }>
      > = {
        pause: api.pause,
        resume: api.resume,
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
          onClick={() => setPending("pause")}
          disabled={isPaused || isKilled || loading !== null}
          className="px-4 py-2 rounded bg-warning/10 text-warning border border-warning/30 text-sm font-mono font-semibold
                     hover:bg-warning/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                     focus-visible:outline-warning"
        >
          {loading === "pause" ? "처리 중..." : "일시정지"}
        </button>

        <button
          onClick={() => setPending("resume")}
          disabled={(!isPaused && !isKilled) || loading !== null}
          className="px-4 py-2 rounded bg-positive/10 text-positive border border-positive/30 text-sm font-mono font-semibold
                     hover:bg-positive/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                     focus-visible:outline-positive"
        >
          {loading === "resume" ? "처리 중..." : "재개"}
        </button>

        <div className="ml-auto">
          <KillSwitchButton onSuccess={onAction} disabled={isKilled} />
        </div>
      </div>

      <ConfirmDialog
        open={pending !== null}
        title={pending === "pause" ? "일시정지" : "재개"}
        message={pending ? CONFIRM_MESSAGE[pending] : ""}
        confirmLabel={pending === "pause" ? "일시정지" : "재개"}
        confirmVariant="warning"
        onConfirm={() => pending && execute(pending)}
        onCancel={() => setPending(null)}
      />

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
