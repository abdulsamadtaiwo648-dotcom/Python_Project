import { useState, type ReactNode } from "react";

/** A small ⓘ that opens a short explanation on tap. Replaces long helper sentences on screen. */
export default function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex align-middle">
      <button type="button" aria-label={`About ${label}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="-mx-3 -my-3 ml-0 inline-flex h-11 w-11 items-center justify-center rounded-full text-[12px] leading-none text-slate-400 hover:text-slate-700">
        ⓘ
      </button>
      {open && (
        <span role="tooltip" className="absolute left-0 top-7 z-20 w-60 rounded-xl border border-slate-200 bg-white p-3 text-left text-xs font-normal leading-5 text-slate-700 shadow-lg">
          {children}
        </span>
      )}
    </span>
  );
}
