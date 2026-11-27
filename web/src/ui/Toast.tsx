import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type Toast = { id: number; text: string; actionLabel?: string; onAction?: () => void };
const ToastContext = createContext<(t: Omit<Toast, "id">) => void>(() => {});

/** Show a short message at the bottom. Use onAction for "Undo" on deletes instead of a confirm popup. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const show = useCallback((t: Omit<Toast, "id">) => {
    window.clearTimeout(timer.current);
    setToast({ ...t, id: Date.now() });
    timer.current = window.setTimeout(() => setToast(null), 5000);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div className="ui-toast" role="status" aria-live="polite">
          <span>{toast.text}</span>
          {toast.actionLabel && toast.onAction && (
            <button type="button" className="ui-toast-action" onClick={() => { toast.onAction?.(); setToast(null); }}>{toast.actionLabel}</button>
          )}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
