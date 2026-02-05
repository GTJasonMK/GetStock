"use client";

import { useEffect, useRef } from "react";

type ConfirmVariant = "primary" | "danger";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: ConfirmVariant;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  variant = "danger",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    const raf = window.requestAnimationFrame(() => cancelRef.current?.focus());
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.cancelAnimationFrame(raf);
    };
  }, [onCancel, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/40 cursor-pointer"
        aria-label="关闭确认弹窗"
        onClick={onCancel}
      />
      <div role="dialog" aria-modal="true" aria-label={title} className="relative w-full max-w-md card bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
            {description && <p className="mt-1 text-sm text-[var(--text-muted)]">{description}</p>}
          </div>
          <button type="button" className="icon-btn -mr-1 -mt-1" onClick={onCancel} aria-label="关闭">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button ref={cancelRef} type="button" className="btn btn-secondary" onClick={onCancel}>
            {cancelText}
          </button>
          <button
            type="button"
            className={`btn ${variant === "danger" ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

