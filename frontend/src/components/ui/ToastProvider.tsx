"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

type ToastVariant = "info" | "success" | "warning" | "error";

type ToastItem = {
  id: string;
  title?: string;
  message: string;
  variant: ToastVariant;
};

type ToastInput = {
  title?: string;
  message: string;
  variant?: ToastVariant;
  durationMs?: number;
};

type ToastContextValue = {
  push: (toast: ToastInput) => void;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return String(Date.now()) + "-" + String(Math.random()).slice(2);
}

function variantStyles(variant: ToastVariant) {
  if (variant === "success") return { border: "border-emerald-200", bg: "bg-emerald-50", icon: "text-emerald-600" };
  if (variant === "warning") return { border: "border-amber-200", bg: "bg-amber-50", icon: "text-amber-600" };
  if (variant === "error") return { border: "border-red-200", bg: "bg-red-50", icon: "text-red-600" };
  return { border: "border-slate-200", bg: "bg-slate-50", icon: "text-slate-600" };
}

function VariantIcon({ variant, className }: { variant: ToastVariant; className: string }) {
  const d =
    variant === "success"
      ? "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      : variant === "warning"
        ? "M12 9v3.75m0 3h.008v.008H12v-.008zM10.29 3.86a1.5 1.5 0 012.42 0l8.4 12.26A1.5 1.5 0 0119.8 18H4.2a1.5 1.5 0 01-1.31-2.88l8.4-12.26z"
        : variant === "error"
          ? "M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          : "M11.25 11.25h1.5V16.5h-1.5v-5.25zm0-3h1.5v1.5h-1.5v-1.5zM21 12a9 9 0 11-18 0 9 9 0 0118 0z";

  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={d} />
    </svg>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast 必须在 ToastProvider 内使用");
  return ctx;
}

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<string, number>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const t = timersRef.current.get(id);
    if (t) window.clearTimeout(t);
    timersRef.current.delete(id);
  }, []);

  const push = useCallback(
    (input: ToastInput) => {
      const id = createId();
      const toast: ToastItem = {
        id,
        title: input.title,
        message: input.message,
        variant: input.variant ?? "info",
      };
      setToasts((prev) => [toast, ...prev].slice(0, 5));

      const durationMs = input.durationMs ?? (toast.variant === "error" ? 6000 : 3500);
      const timer = window.setTimeout(() => dismiss(id), Math.max(1000, durationMs));
      timersRef.current.set(id, timer);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ push, dismiss }), [dismiss, push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="fixed top-4 right-4 z-[9999] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2"
        aria-live="polite"
        aria-relevant="additions removals"
      >
        {toasts.map((t) => {
          const s = variantStyles(t.variant);
          return (
            <div
              key={t.id}
              className={`card flex items-start gap-3 p-4 ${s.border} ${s.bg} motion-safe:transition-colors motion-safe:duration-200`}
              role={t.variant === "error" ? "alert" : "status"}
            >
              <VariantIcon variant={t.variant} className={`mt-0.5 h-5 w-5 ${s.icon}`} />
              <div className="min-w-0 flex-1">
                {t.title && <div className="text-sm font-semibold text-[var(--text-primary)]">{t.title}</div>}
                <div className="text-sm text-[var(--text-muted)] break-words">{t.message}</div>
              </div>
              <button type="button" className="icon-btn -mr-1 -mt-1" onClick={() => dismiss(t.id)} aria-label="关闭提示">
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

