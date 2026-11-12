import { OctagonX, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ApiResponse, BotStatus } from "../api/types";
import { HALT_META, TONE_CLASS } from "../lib/halt";
import { cn } from "../lib/utils";
import { ConfirmDialog } from "./ConfirmDialog";

type Action = "pause" | "resume" | "kill";

const ACTION: Record<
  Action,
  {
    title: string;
    message: string;
    confirmLabel: string;
    variant: "live" | "warn" | "danger";
    run: () => Promise<ApiResponse>;
  }
> = {
  pause: {
    title: "봇 일시정지",
    message:
      "신규 진입을 멈춥니다. 기존 포지션과 미체결 주문은 그대로 유지됩니다.",
    confirmLabel: "일시정지",
    variant: "warn",
    run: api.pause,
  },
  resume: {
    title: "봇 재개",
    message: "정상 운용으로 돌아갑니다. 시그널이 나오면 다시 주문이 나갑니다.",
    confirmLabel: "재개",
    variant: "live",
    run: api.resume,
  },
  kill: {
    title: "킬스위치 활성화",
    message:
      "모든 신규 주문을 즉시 차단합니다. 손절 주문만 허용됩니다.\n다시 가동하려면 직접 재개해야 합니다.",
    confirmLabel: "킬스위치 활성화",
    variant: "danger",
    run: api.kill,
  },
};

const FEEDBACK_TTL_MS = 6_000;

interface Props {
  status: BotStatus | null;
  /** 조작이 끝난 직후 상태를 즉시 다시 읽기 위한 콜백 */
  onAction: () => void;
}

/**
 * 봇 제어의 유일한 진입점 — 헤더에 고정돼 어느 화면에서든 한 번에 닿는다.
 * 같은 버튼을 여러 화면에 복제하지 않는다(위치가 둘이면 상태도 둘이 된다).
 */
export function BotControls({ status, onAction }: Props) {
  const [pending, setPending] = useState<Action | null>(null);
  const [running, setRunning] = useState<Action | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(
    null,
  );

  // 성공 메시지만 자동으로 걷는다 — 실패는 다음 조작 전까지 남겨 놓쳐서는 안 된다
  useEffect(() => {
    if (!feedback?.ok) return;
    const id = setTimeout(() => setFeedback(null), FEEDBACK_TTL_MS);
    return () => clearTimeout(id);
  }, [feedback]);

  async function execute(action: Action) {
    setPending(null);
    setRunning(action);
    setFeedback(null);
    try {
      const res = await ACTION[action].run();
      setFeedback({
        ok: res.success,
        msg: res.message || (res.success ? "완료" : "요청이 거부됐습니다"),
      });
      if (res.success) onAction();
    } catch (e: unknown) {
      setFeedback({
        ok: false,
        msg: e instanceof Error ? e.message : "오류 발생",
      });
    } finally {
      setRunning(null);
    }
  }

  const halt = status?.halt_level;
  const meta = halt ? HALT_META[halt] : null;
  const isStopped = halt === "pause" || halt === "kill";
  const toggle: Action = isStopped ? "resume" : "pause";
  const isBusy = running !== null;
  const dialog = pending ? ACTION[pending] : null;

  return (
    <div className="relative flex items-center gap-2">
      <span
        className={cn(
          "inline-flex h-8 items-center gap-2 whitespace-nowrap rounded-md border px-2.5 text-xs font-semibold",
          meta ? TONE_CLASS[meta.tone].pill : "border-line text-muted",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            meta ? TONE_CLASS[meta.tone].dot : "bg-muted",
            halt === "none" && "animate-pulse",
          )}
        />
        {meta?.label ?? "연결 중…"}
      </span>

      <button
        type="button"
        onClick={() => setPending(toggle)}
        disabled={!status || isBusy}
        className={cn("btn", toggle === "resume" ? "btn-live" : "btn-warn")}
      >
        {toggle === "resume" ? (
          <Play aria-hidden="true" className="h-3.5 w-3.5" />
        ) : (
          <Pause aria-hidden="true" className="h-3.5 w-3.5" />
        )}
        {running === toggle
          ? "처리 중…"
          : toggle === "resume"
            ? "재개"
            : "일시정지"}
      </button>

      {/* 구분선으로 떨어뜨려 놓는다 — 구조적 거리가 위험도를 전달한다 */}
      <span aria-hidden="true" className="h-5 w-px bg-line-strong" />

      <button
        type="button"
        onClick={() => setPending("kill")}
        disabled={!status || halt === "kill" || isBusy}
        className="btn btn-danger"
      >
        <OctagonX aria-hidden="true" className="h-3.5 w-3.5" />
        {running === "kill" ? "처리 중…" : "킬스위치"}
      </button>

      {feedback && (
        <p
          role={feedback.ok ? "status" : "alert"}
          className={cn(
            "absolute right-0 top-full z-[var(--z-dropdown)] mt-2 w-max max-w-xs rounded-md border bg-raised px-3 py-2 text-xs shadow-lg shadow-black/40",
            "animate-[rise-in_0.18s_var(--ease-out)]",
            feedback.ok
              ? "border-live/40 text-live"
              : "border-danger/50 text-danger",
          )}
        >
          {feedback.ok ? "완료 — " : "실패 — "}
          {feedback.msg}
        </p>
      )}

      <ConfirmDialog
        open={dialog !== null}
        title={dialog?.title ?? ""}
        message={
          dialog
            ? status?.env === "prod"
              ? `${dialog.message}\n\n실전투자 환경입니다. 실제 계좌에 바로 반영됩니다.`
              : dialog.message
            : ""
        }
        confirmLabel={dialog?.confirmLabel ?? ""}
        confirmVariant={dialog?.variant ?? "warn"}
        onConfirm={() => pending && execute(pending)}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
