import type { ReactNode } from "react";
import Sheet from "../components/Sheet";
import { ListRow } from "./ListRow";

export type ActionOption = { label: string; sub?: string; icon?: ReactNode; onSelect: () => void };

/** A small sheet of choices, used by the floating + buttons (e.g. Sale, Expense, Money in). */
export default function ActionSheet({ title, options, onClose }: { title: string; options: ActionOption[]; onClose: () => void }) {
  return (
    <Sheet title={title} onClose={onClose} compact>
      <div className="sb-sheet-body" style={{ display: "flex", flexDirection: "column", gap: "var(--sb-space-1)", paddingBottom: "var(--sb-space-4)" }}>
        {options.map((o) => (
          <ListRow key={o.label} icon={o.icon} title={o.label} subtitle={o.sub} onClick={() => { o.onSelect(); onClose(); }} />
        ))}
      </div>
    </Sheet>
  );
}
