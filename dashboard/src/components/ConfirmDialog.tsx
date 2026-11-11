import { useEffect, useRef } from "react";

type ConfirmVariant = "live" | "warn" | "danger";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  confirmVariant: ConfirmVariant;
  onConfirm: () => void;
  onCancel: () => void;
}

const CONFIRM_CLASS: Record<ConfirmVariant, string> = {
  live: "btn btn-live",
  warn: "btn btn-warn",
  danger: "btn btn-danger",
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

    // ESC(cancel 이벤트) 및 backdrop 클릭(click 이벤트) 모두 onCancel() 호출.
    // close 이벤트는 취소가 아니라 트리거 버튼으로 포커스 복귀 전용.
    function handleCancel(e: Event) {
      e.preventDefault();
      onCancel();
    }
    function handleClose() {
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
      className="rounded-lg border border-line-strong bg-raised p-0 text-ink shadow-2xl shadow-black/60
                 backdrop:bg-black/60 open:animate-[rise-in_0.18s_var(--ease-out)]"
    >
      <div className="w-[22rem] max-w-[90vw] space-y-3 p-5">
        <h2 id="confirm-dialog-title" className="text-base font-semibold">
          {title}
        </h2>
        <p
          id="confirm-dialog-message"
          className="whitespace-pre-line text-data leading-relaxed text-dim"
        >
          {message}
        </p>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} className="btn">
            취소
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={CONFIRM_CLASS[confirmVariant]}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
