import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { parseCsv, toObjects, type ImportKind } from "../csv";
import Sheet from "./Sheet";

type RowStatus = "ok" | "error" | "duplicate";
interface PreviewRow { row: number; status: RowStatus; reasons: string[]; duplicate_of: { kind: string } | null }
interface Result { batch_id: number | null; imported: number; skipped: { row: number; reason: string }[]; already_imported?: boolean }
interface Batch { id: number; kind: ImportKind; status: string; created_at: string | null; records: number }
interface UndoPlan { remove: Record<string, number>; keep: { table: string; id: number; reason: string }[] }

const MAX_BYTES = 1024 * 1024;
const MAX_ROWS = 500;

const TITLES: Record<ImportKind, string> = {
  expenses: "expenses",
  sales: "sales",
  money_in: "money in",
};

const HELP: Record<ImportKind, string> = {
  expenses: "Columns: date, amount, category, description, and optionally paid_from (an account name; blank uses the default account).",
  sales: "Columns: date, description, amount, and optionally customer and payment_mode (Cash, POS, Transfer, Card, Credit). Each sale is recorded as paid.",
  money_in: "Columns: date, amount, type (Owner contribution, Loan, Refund received, Other income or Transfer), and optionally received_into, from_account and description. A transfer needs both accounts.",
};

/** Import a spreadsheet saved as CSV: preview, keep any genuine repeats, import, and undo the batch. */
export default function ImportSheet(props: { kind: ImportKind; onDone: () => void; onClose: () => void }) {
  const { kind } = props;
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<PreviewRow[] | null>(null);
  const [keep, setKeep] = useState<Set<number>>(new Set());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [undo, setUndo] = useState<{ batchId: number; plan: UndoPlan } | null>(null);
  const [undone, setUndone] = useState<string>("");
  const batchKey = useRef<string>("");

  async function pick(file: File | undefined) {
    setError(""); setResult(null); setRows([]); setPreview(null); setKeep(new Set());
    if (!file) return;
    if (file.size > MAX_BYTES) return setError("That file is larger than 1 MB. Split it into smaller files.");
    if (!/\.csv$/i.test(file.name)) return setError("Save your spreadsheet as a CSV file (in Excel or Google Sheets: File, Save as, CSV).");
    const { rows: parsed, missing } = toObjects(kind, parseCsv(await file.text()));
    if (missing.length) return setError(`The first row must have these columns: ${missing.join(", ")}.`);
    if (!parsed.length) return setError("No rows found under the header row.");
    if (parsed.length > MAX_ROWS) return setError(`Import at most ${MAX_ROWS} rows at a time. This file has ${parsed.length}; split it.`);
    setFileName(file.name);
    setRows(parsed);
    batchKey.current = crypto.randomUUID ? crypto.randomUUID() : `b-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await checkRows(parsed);
  }

  async function checkRows(list: Record<string, string>[]) {
    setBusy(true);
    try {
      const res = await api.post<{ rows: PreviewRow[] }>("/api/import/preview", { kind, rows: list });
      setPreview(res.rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not check the file. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function toggleKeep(row: number) {
    setKeep((prev) => {
      const next = new Set(prev);
      if (next.has(row)) next.delete(row); else next.add(row);
      return next;
    });
  }

  async function run() {
    setBusy(true);
    setError("");
    try {
      const res = await api.post<Result>("/api/import/commit", {
        kind, rows, batch_key: batchKey.current, keep_rows: [...keep],
      });
      setResult(res);
      props.onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The import did not finish. Nothing was half-imported; check the file and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function showUndo(batchId: number) {
    setError(""); setUndone("");
    try {
      const plan = await api.get<UndoPlan & { status: string }>(`/api/import-batches/${batchId}/undo`);
      setUndo({ batchId, plan });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not check the undo. Try again.");
    }
  }

  async function doUndo() {
    if (!undo) return;
    setBusy(true);
    try {
      const res = await api.post<{ message: string; removed: Record<string, number> | null }>(`/api/import-batches/${undo.batchId}/undo`);
      setUndone(res.message);
      setUndo(null);
      setResult(null);
      props.onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not undo the import. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const counts = preview ? {
    ok: preview.filter((r) => r.status === "ok").length,
    errors: preview.filter((r) => r.status === "error").length,
    duplicates: preview.filter((r) => r.status === "duplicate").length,
  } : null;
  const toImport = preview ? preview.filter((r) => r.status === "ok" || (r.status === "duplicate" && keep.has(r.row))).length : 0;

  return (
    <Sheet title={`Import ${TITLES[kind]} from a spreadsheet`} onClose={props.onClose}>
      <div className="sb-sheet-body">
        <p className="sb-help">Save your sheet as a CSV file. The first row must be headings. {HELP[kind]} Dates are YYYY-MM-DD, up to two years back and not in the future.</p>
        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
        {undone && <p role="status" className="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">{undone}</p>}

        {!result && (
          <div className="sb-field">
            <label htmlFor="import-file">CSV file</label>
            <input id="import-file" type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => void pick(e.target.files?.[0])} />
          </div>
        )}

        {preview && counts && !result && (
          <>
            <p className="mt-3 text-sm text-slate-700">
              <strong>{fileName}</strong>: {counts.ok} ready, {counts.duplicates} already recorded or repeated, {counts.errors} need correcting.
              Nothing has been imported yet.
            </p>
            <div className="table-wrap mt-2 max-h-72 overflow-y-auto">
              <table aria-label="Checked rows">
                <thead><tr><th>Row</th><th>Status</th><th>Details</th><th>Keep</th></tr></thead>
                <tbody>
                  {preview.map((r) => (
                    <tr key={r.row}>
                      <td>{r.row}</td>
                      <td>
                        <span className={r.status === "ok" ? "text-emerald-700" : r.status === "error" ? "text-rose-700" : "text-amber-700"}>
                          {r.status === "ok" ? "Ready" : r.status === "error" ? "Needs correcting" : "Possible repeat"}
                        </span>
                      </td>
                      <td className="text-xs">{r.reasons.join(" ")}</td>
                      <td>
                        {r.status === "duplicate" && (
                          <label className="flex items-center gap-1 text-xs">
                            <input type="checkbox" checked={keep.has(r.row)} onChange={() => toggleKeep(r.row)} />
                            Genuine repeat
                          </label>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="sb-sheet-foot">
              <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose} disabled={busy}>Cancel</button>
              <button type="button" className="sb-btn sb-btn-primary" onClick={() => void run()} disabled={busy || toImport === 0}>
                {busy ? "Importing…" : `Import ${toImport} ${toImport === 1 ? "row" : "rows"}`}
              </button>
            </div>
          </>
        )}

        {result && (
          <div className="mt-3 text-sm">
            <p className="font-semibold text-slate-900">
              {result.already_imported ? "This file was already imported." : `${result.imported} ${TITLES[kind]} imported.`} {result.skipped.length} skipped.
            </p>
            {result.skipped.length > 0 && (
              <ul className="mt-2 max-h-56 list-none overflow-y-auto text-xs text-slate-600" aria-label="Rows skipped">
                {result.skipped.map((s) => <li key={s.row}>Row {s.row}: {s.reason}</li>)}
              </ul>
            )}
            {result.batch_id && !result.already_imported && (
              <div className="sb-sheet-foot">
                <button type="button" className="sb-btn sb-btn-secondary" onClick={() => void showUndo(result.batch_id!)}>Undo this import</button>
                <button type="button" className="sb-btn sb-btn-primary" onClick={props.onClose}>Done</button>
              </div>
            )}
          </div>
        )}

        {undo && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
            <p className="font-semibold">Undo this import?</p>
            <p className="text-xs">This removes: {Object.entries(undo.plan.remove).filter(([, n]) => n > 0).map(([t, n]) => `${n} ${t.replace("_", " ")}`).join(", ") || "nothing"}.</p>
            {undo.plan.keep.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-xs">
                {undo.plan.keep.map((k) => <li key={`${k.table}-${k.id}`}>Kept: {k.table.replace("_", " ")} {k.id}. {k.reason}.</li>)}
              </ul>
            )}
            <div className="sb-sheet-foot">
              <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setUndo(null)} disabled={busy}>Keep the import</button>
              <button type="button" className="sb-btn sb-btn-danger" onClick={() => void doUndo()} disabled={busy}>Undo import</button>
            </div>
          </div>
        )}

        {!result && !preview && !busy && <RecentImports kind={kind} onUndo={(id) => void showUndo(id)} />}
      </div>
    </Sheet>
  );
}

function RecentImports({ kind, onUndo }: { kind: ImportKind; onUndo: (id: number) => void }) {
  const [batches, setBatches] = useState<Batch[] | null>(null);
  useEffect(() => {
    api.get<{ batches: Batch[] }>("/api/import-batches")
      .then((res) => setBatches(res.batches.filter((b) => b.kind === kind)))
      .catch(() => setBatches([]));
  }, [kind]);
  if (!batches || batches.length === 0) return null;
  return (
    <div className="mt-6 border-t border-slate-100 pt-4">
      <h4 className="text-sm font-semibold text-slate-800">Recent imports</h4>
      <ul className="mt-2 space-y-2 text-xs">
        {batches.slice(0, 5).map((b) => (
          <li key={b.id} className="flex items-center justify-between gap-2">
            <span>{b.created_at ? b.created_at.slice(0, 10) : ""} · {b.records} records · {b.status === "undone" ? "undone" : "imported"}</span>
            {b.status === "committed" && <button type="button" className="sb-link" onClick={() => onUndo(b.id)}>Undo</button>}
          </li>
        ))}
      </ul>
    </div>
  );
}
