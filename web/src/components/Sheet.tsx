import { useEffect, useRef, type ReactNode } from "react";

/** The design's modal: a bottom/full-screen sheet on phones, a card on desktop. */
export default function Sheet(props: {
  title: string; onClose: () => void; children: ReactNode; compact?: boolean; id?: string; description?: ReactNode;
}) {
  const close = useRef(props.onClose);
  close.current = props.onClose;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, []);
  return (
    <div className="sb-modal" role="dialog" aria-modal="true" aria-label={props.title}
      onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <div id={props.id} className={`sb-sheet ${props.compact ? "sb-sheet-compact" : ""}`}>
        <div className="sb-sheet-head">
          <div>
            <h3 className="sb-sheet-title">{props.title}</h3>
            {props.description}
          </div>
          <button type="button" className="sb-icon-btn" aria-label="Close" onClick={props.onClose}>
            <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </div>
        {props.children}
      </div>
    </div>
  );
}
