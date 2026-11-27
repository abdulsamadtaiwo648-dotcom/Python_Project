import type { ReactNode } from "react";

/** One row: optional leading icon, title and subtitle, and a right-hand amount. */
export function ListRow({ icon, title, subtitle, amount, tone, onClick, trailing }: {
  icon?: ReactNode; title: string; subtitle?: string; amount?: string; tone?: "money-in"; onClick?: () => void; trailing?: ReactNode;
}) {
  const content = (
    <>
      {icon}
      <div className="ui-row-main">
        <div className="ui-row-title">{title}</div>
        {subtitle && <div className="ui-row-sub">{subtitle}</div>}
      </div>
      {amount && <div className={`ui-row-amount ${tone ? `is-${tone}` : ""}`}>{amount}</div>}
      {trailing}
    </>
  );
  return onClick ? (
    <button type="button" onClick={onClick} className="ui-row" style={{ width: "100%", textAlign: "left", background: "none", border: 0 }}>{content}</button>
  ) : (
    <div className="ui-row">{content}</div>
  );
}

/** Groups rows under a sticky day header with the day's total. Input is already sorted, newest first. */
export function DayGroup({ label, total, children }: { label: string; total?: string; children: ReactNode }) {
  return (
    <div>
      <div className="ui-day-head"><span>{label}</span>{total && <span>{total}</span>}</div>
      {children}
    </div>
  );
}
