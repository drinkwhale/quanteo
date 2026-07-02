import { useState } from "react";
import { api } from "../api/client";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  onSuccess?: () => void;
  disabled?: boolean;
  fullWidth?: boolean;
}

/**
 * 킬스위치 버튼 — ControlPanel과 StrategyPage 양쪽에서 공유 (T092)
 * 클릭 시 ConfirmDialog로 확인 후 /kill API 호출.
 */
export function KillSwitchButton({ onSuccess, disabled, fullWidth }: Props) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setConfirmOpen(false);
    setLoading(true);
    setError(null);
    try {
      const res = await api.kill();
      if (!res.success) {
        setError(res.message || "킬스위치 활성화 실패");
        return;
      }
      setDone(true);
      onSuccess?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={fullWidth ? "w-full space-y-2" : "space-y-2"}>
      <button
        type="button"
        onClick={() => setConfirmOpen(true)}
        disabled={disabled || loading || done}
        className={`${fullWidth ? "w-full" : ""} py-2 px-4 rounded bg-negative/10 text-negative border border-negative/30 text-sm font-mono font-semibold
                   hover:bg-negative/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                   focus-visible:outline-negative`}
      >
        {done ? "킬스위치 활성화됨" : loading ? "처리 중..." : "킬스위치"}
      </button>

      {error && (
        <p className="text-xs font-mono text-negative bg-negative/5 border border-negative/20 rounded px-3 py-2">
          {error}
        </p>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="킬스위치 활성화"
        message="⚠️ 킬스위치를 활성화하면 모든 신규 주문이 차단됩니다. 계속하겠습니까?"
        confirmLabel="킬스위치 활성화"
        confirmVariant="danger"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
