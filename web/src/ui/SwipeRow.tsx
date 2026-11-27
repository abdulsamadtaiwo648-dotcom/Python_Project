import { useRef, useState, type ReactNode } from "react";

const REVEAL = 144; // width of the two action buttons together

/**
 * Swipe a row left to reveal Edit and Delete. The buttons are always in the page too, so the same
 * actions work with a keyboard or a screen reader. Swiping back, or tapping the row, closes it.
 */
export default function SwipeRow({ children, onEdit, onDelete, label }: {
  children: ReactNode; onEdit: () => void; onDelete: () => void; label: string;
}) {
  const [offset, setOffsetState] = useState(0);
  // The latest offset, read by the pointer handlers. Handlers can run before a re-render shows the newest value.
  const current = useRef(0);
  const start = useRef<number | null>(null);
  const base = useRef(0);
  // True after a real drag, so the click the browser fires at the end of the drag is ignored.
  const dragged = useRef(false);
  const setOffset = (value: number) => { current.current = value; setOffsetState(value); };
  const open = offset <= -REVEAL / 2;

  function down(e: React.PointerEvent) {
    start.current = e.clientX;
    dragged.current = false;
    base.current = current.current <= -REVEAL / 2 ? -REVEAL : 0;
  }
  function move(e: React.PointerEvent) {
    if (start.current === null) return;
    const dx = e.clientX - start.current;
    if (Math.abs(dx) < 4 && current.current === 0) return;
    if (Math.abs(dx) >= 4) dragged.current = true;
    setOffset(Math.min(0, Math.max(-REVEAL, base.current + dx)));
  }
  function up() {
    start.current = null;
    setOffset(current.current <= -REVEAL / 2 ? -REVEAL : 0);
  }

  return (
    <div className="ui-swipe" aria-label={label}>
      <div className="ui-swipe-actions">
        <button type="button" className="ui-swipe-edit" onClick={() => { setOffset(0); onEdit(); }}>Edit</button>
        <button type="button" className="ui-swipe-delete" onClick={() => { setOffset(0); onDelete(); }}>Delete</button>
      </div>
      <div className="ui-swipe-row" style={{ transform: `translateX(${offset}px)` }}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
        onClickCapture={(e) => {
          if (dragged.current) { dragged.current = false; e.preventDefault(); e.stopPropagation(); return; }
          if (open) { e.preventDefault(); e.stopPropagation(); setOffset(0); }
        }}>
        {children}
      </div>
    </div>
  );
}
