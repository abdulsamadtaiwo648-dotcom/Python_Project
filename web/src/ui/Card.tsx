import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`ui-card ${className}`.trim()}>{children}</section>;
}

/** Label, big value, and an optional small note such as the change vs last period. Tone colours the value. */
export function StatCard({ label, value, note, tone, info, footer, onClick }: {
  label: string; value: string | null; note?: string; tone?: "money-in" | "warning" | "danger"; info?: ReactNode; footer?: ReactNode; onClick?: () => void;
}) {
  const body = (
    <>
      <div className="ui-stat-label"><span>{label}</span>{info}</div>
      {value === null ? (
        <div className="ui-skeleton" aria-hidden="true" />
      ) : (
        <div className={`ui-stat-value ${tone ? `is-${tone}` : ""}`}>{value}</div>
      )}
      {note && <div className="ui-stat-note">{note}</div>}
      {footer && <div className="ui-stat-footer">{footer}</div>}
    </>
  );
  return onClick ? (
    <button type="button" onClick={onClick} className="ui-card ui-stat" style={{ textAlign: "left" }}>{body}</button>
  ) : (
    <section className="ui-card ui-stat">{body}</section>
  );
}
