import { useId, useState } from "react";
import Sheet from "../components/Sheet";

/** A select that opens as a sheet on phones: big rows, the current choice ticked. */
export default function SelectSheet<T extends string>({ label, value, options, onChange, placeholder = "Choose" }: {
  label: string; value: T | ""; options: { value: T; label: string }[]; onChange: (v: T) => void; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const current = options.find((o) => o.value === value);
  return (
    <div>
      <span id={`${id}-label`} className="ui-stat-label">{label}</span>
      <button type="button" aria-haspopup="dialog" aria-labelledby={`${id}-label ${id}-value`} className="ui-input"
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", textAlign: "left", marginTop: "var(--sb-space-1)" }}
        onClick={() => setOpen(true)}>
        <span id={`${id}-value`} style={{ color: current ? "var(--sb-ink)" : "var(--sb-muted)" }}>{current?.label ?? placeholder}</span>
        <span aria-hidden="true" style={{ color: "var(--sb-muted)" }}>▾</span>
      </button>
      {open && (
        <Sheet title={label} onClose={() => setOpen(false)} compact>
          <div className="sb-sheet-body" role="listbox" aria-label={label} style={{ display: "flex", flexDirection: "column", gap: "var(--sb-space-1)" }}>
            {options.map((o) => (
              <button key={o.value} type="button" role="option" aria-selected={o.value === value} className="ui-row"
                style={{ width: "100%", textAlign: "left", background: "none", border: 0, padding: "0 var(--sb-space-2)" }}
                onClick={() => { onChange(o.value); setOpen(false); }}>
                <span className="ui-row-main ui-row-title">{o.label}</span>
                {o.value === value && <span aria-hidden="true" style={{ color: "var(--sb-brand)", fontWeight: 700 }}>✓</span>}
              </button>
            ))}
          </div>
        </Sheet>
      )}
    </div>
  );
}
