import { useEffect, useRef } from "react";

type ConfirmVariant = "warning" | "danger";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  confirmVariant: ConfirmVariant;
  onConfirm: () => void;
  onCancel: () => void;
}

const CONFIRM_STYLE: Record<ConfirmVariant, string> = {
  warning:
    "bg-warning/10 text-warning border-warning/30 hover:bg-warning/20 focus-visible:outline-warning",
  danger:
    "bg-negative/10 text-negative border-negative/30 hover:bg-negative/20 focus-visible:outline-negative",
};

/**
 * 접근 가능한 확인 모달. window.confirm() 대체 (T087)
 * native <dialog> 기반 — 별도 포털/z-index 관리 불필요, 브라우저가 top-layer로 렌더링.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  confirmVariant,
  onConfirm,
  onCancel,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<Element | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      triggerRef.current = document.activeElement;
      if (!dialog.open) dialog.showModal();
      confirmRef.current?.focus();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    // ESC(cancel 이벤트) 및 backdrop 클릭(close 이벤트) 모두 취소로 처리
    function handleCancel(e: Event) {
      e.preventDefault();
      onCancel();
    }
    function handleClose() {
      // 트리거 버튼으로 포커스 복귀
      if (triggerRef.current instanceof HTMLElement) {
        triggerRef.current.focus();
      }
    }
    function handleBackdropClick(e: MouseEvent) {
      if (e.target === dialog) onCancel();
    }

    dialog.addEventListener("cancel", handleCancel);
    dialog.addEventListener("close", handleClose);
    dialog.addEventListener("click", handleBackdropClick);
    return () => {
      dialog.removeEventListener("cancel", handleCancel);
      dialog.removeEventListener("close", handleClose);
      dialog.removeEventListener("click", handleBackdropClick);
    };
  }, [onCancel]);

  return (
    <dialog
      ref={dialogRef}
      role="alertdialog"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-message"
      className="bg-panel border border-border rounded-lg p-0 text-white backdrop:bg-black/60
                 animate-[fadeIn_0.15s_ease-out] motion-reduce:animate-none open:motion-reduce:opacity-100"
    >
      <div className="w-80 max-w-[90vw] p-4 space-y-4 font-mono">
        <h2
          id="confirm-dialog-title"
          className="text-sm font-semibold tracking-wider"
        >
          {title}
        </h2>
        <p
          id="confirm-dialog-message"
          className="text-xs text-muted leading-relaxed"
        >
          {message}
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded border border-border text-xs font-semibold text-muted
                       hover:text-white hover:border-structural-line transition-colors focus-visible:outline-accent"
          >
            취소
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`px-4 py-2 rounded border text-xs font-semibold transition-colors ${CONFIRM_STYLE[confirmVariant]}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
