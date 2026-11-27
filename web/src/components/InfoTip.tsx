import { useState, type ReactNode } from "react";
import Sheet from "./Sheet";

/** A small ⓘ that opens a short explanation in a sheet. Replaces long helper sentences on screen. */
export default function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex align-middle">
      <button type="button" aria-label={`About ${label}`} aria-haspopup="dialog" onClick={() => setOpen(true)}
        className="-mx-3 -my-3 ml-0 inline-flex h-11 w-11 items-center justify-center rounded-full text-[12px] leading-none text-slate-400 hover:text-slate-700">
        ⓘ
      </button>
      {open && (
        <Sheet title={label} onClose={() => setOpen(false)} compact>
          <div className="sb-sheet-body" style={{ fontSize: "var(--sb-text-body)", lineHeight: 1.5, color: "var(--sb-ink)" }}>{children}</div>
        </Sheet>
      )}
    </span>
  );
}
