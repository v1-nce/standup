"use client";

import { useEffect, useRef } from "react";

const BTN =
  "press border border-ink px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-[0.08em] shadow-hard";

/** A destructive-action confirmation in the app's own frame, not the browser's. */
export function ConfirmDialog({
  confirmLabel = "Confirm",
  description,
  onClose,
  onConfirm,
  title,
}: {
  confirmLabel?: string;
  description?: string;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
}) {
  const frame = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = frame.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={frame}
      className="m-auto flex w-[min(24rem,92vw)] flex-col border border-ink bg-paper p-4 text-ink shadow-hard backdrop:bg-ink-faint"
      onClose={onClose}
    >
      <p className="font-mono text-sm font-bold leading-relaxed">{title}</p>
      {description && (
        <p className="mt-1 font-mono text-sm leading-relaxed text-ink-soft">{description}</p>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <button
          className={`${BTN} bg-paper enabled:hover:bg-ink enabled:hover:text-paper`}
          onClick={onClose}
          type="button"
        >
          Cancel
        </button>
        <button
          className={`${BTN} bg-ink text-paper enabled:hover:bg-paper enabled:hover:text-ink`}
          onClick={onConfirm}
          type="button"
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
