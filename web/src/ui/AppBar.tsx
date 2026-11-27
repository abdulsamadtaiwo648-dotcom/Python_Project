import type { ReactNode } from "react";

/** Title with an optional back button and an optional right-hand action. */
export default function AppBar({ title, onBack, action }: { title: string; onBack?: () => void; action?: ReactNode }) {
  return (
    <header className="ui-appbar">
      {onBack && (
        <button type="button" className="ui-appbar-icon" aria-label="Back" onClick={onBack}>
          <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="m15 6-6 6 6 6" /></svg>
        </button>
      )}
      <h1 className="ui-appbar-title">{title}</h1>
      {action}
    </header>
  );
}
