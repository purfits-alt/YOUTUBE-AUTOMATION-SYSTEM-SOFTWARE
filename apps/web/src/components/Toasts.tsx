import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { t } from "../i18n";
import { Icon } from "./icons";

interface Toast {
  id: number;
  message: string;
  tone: "ok" | "danger";
}

const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => undefined);

export function useToast() {
  return useContext(ToastContext);
}

/** Toasts last 4 s and are announced through an ARIA live region (FRONTEND_SPECIFICATION §0.3). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((x) => x.id !== id)), []);
  const show = useCallback(
    (message: string, tone: Toast["tone"] = "ok") => {
      const id = next.current++;
      setToasts((all) => [...all, { id, message, tone }]);
      window.setTimeout(() => dismiss(id), 4000);
    },
    [dismiss],
  );
  const value = useMemo(() => show, [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        role="status"
        className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-4 sm:items-end"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            data-testid="toast"
            className={`tf-rise pointer-events-auto flex max-w-sm items-start gap-3 rounded-xl border px-3 py-2.5 text-sm shadow-xl ${
              toast.tone === "danger"
                ? "border-danger bg-danger-soft text-danger-text"
                : "border-line bg-surface text-fg"
            }`}
          >
            <span
              aria-hidden="true"
              className={`grid size-5 shrink-0 place-items-center rounded-full ${toast.tone === "danger" ? "bg-danger text-white" : "bg-accent text-accent-fg"}`}
            >
              <Icon name={toast.tone === "danger" ? "alert" : "check"} className="size-3" />
            </span>
            <span>{toast.message}</span>
            <button type="button" aria-label={t("toast.close")} onClick={() => dismiss(toast.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
