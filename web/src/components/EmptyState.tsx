import type { ReactNode } from "react";

/** One friendly line and one button, for a list with nothing in it yet. */
export default function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="text-sm text-slate-600">{message}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
