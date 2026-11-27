import Sheet from "../components/Sheet";
import Button from "./Button";

/** For destructive actions only. Everything else uses an Undo toast. */
export default function ConfirmSheet({ title, text, confirmLabel, onConfirm, onCancel, busy }: {
  title: string; text: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; busy?: boolean;
}) {
  return (
    <Sheet title={title} onClose={onCancel} compact>
      <div className="sb-sheet-body">
        <p style={{ fontSize: "var(--sb-text-body)", color: "var(--sb-muted)" }}>{text}</p>
        <div style={{ display: "flex", gap: "var(--sb-space-2)", marginTop: "var(--sb-space-4)" }}>
          <Button block onClick={onCancel}>Keep it</Button>
          <Button block variant="danger" disabled={busy} onClick={onConfirm}>{busy ? "Working…" : confirmLabel}</Button>
        </div>
      </div>
    </Sheet>
  );
}
