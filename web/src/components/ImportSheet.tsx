import { useState } from "react";
import { ApiError, api } from "../api";
import Sheet from "./Sheet";

export type ImportKind = "expenses" | "sales";

interface Skip { row: number; reason: string }
interface Result { imported: number; skipped: Skip[] }

const MAX_BYTES = 1024 * 1024;   // 1 MB
const MAX_ROWS = 2000;
const BATCH = 200;               // the server takes this many rows per request

const COLUMNS: Record<ImportKind, { required: string[]; optional: string[] }> = {
  expenses: { required: ["date", "amount", "category", "description"], optional: [] },
  sales: { required: ["date", "description", "amount"], optional: ["customer", "payment_mode"] },
};

/** A small CSV reader: quoted fields, commas and line breaks inside quotes, CRLF or LF. */
export function parseCsv(text: string): string[][] {
  const src = text.replace(/^﻿/, "");
  const rows: string[][] = [];
  let row: string[] = [], field = "", quoted = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (quoted) {
      if (ch === '"' && src[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((c) => c.trim() !== "")) rows.push(row);
      row = [];
    } else field += ch;
  }
  row.push(field);
  if (row.some((c) => c.trim() !== "")) rows.push(row);
  return rows;
}

/** Turns CSV rows into objects keyed by lowercase header, or explains what is missing. */
export function toObjects(kind: ImportKind, table: string[][]): { rows: Record<string, string>[]; missing: string[] } {
  if (table.length < 2) return { rows: [], missing: [] };
  const headers = table[0].map((h) => h.trim().toLowerCase().replace(/\s+/g, "_"));
  const missing = COLUMNS[kind].required.filter((c) => !headers.includes(c));
  if (missing.length) return { rows: [], missing };
  const rows = table.slice(1).map((cells) => {
    const obj: Record<string, string> = {};
    headers.forEach((h, i) => { obj[h] = (cells[i] ?? "").trim(); });
    return obj;
  });
  return { rows, missing: [] };
}

export default function ImportSheet(props: { kind: ImportKind; onDone: () => void; onClose: () => void }) {
  const { kind } = props;
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  async function pick(file: File | undefined) {
    setError("");
    setResult(null);
    setRows([]);
    if (!file) return;
    if (file.size > MAX_BYTES) return setError("That file is larger than 1 MB. Split it into smaller files.");
    if (!/\.csv$/i.test(file.name)) return setError("Save your spreadsheet as a CSV file (in Excel or Google Sheets: File, Save as, CSV).");
    const { rows: parsed, missing } = toObjects(kind, parseCsv(await file.text()));
    if (missing.length) return setError(`The first row must have these columns: ${missing.join(", ")}.`);
    if (!parsed.length) return setError("No rows found under the header row.");
    if (parsed.length > MAX_ROWS) return setError(`Import at most ${MAX_ROWS} rows at a time. This file has ${parsed.length}.`);
    setFileName(file.name);
    setRows(parsed);
  }

  async function run() {
    setBusy(true);
    setError("");
    const total: Result = { imported: 0, skipped: [] };
    try {
      for (let start = 0; start < rows.length; start += BATCH) {
        const batch = rows.slice(start, start + BATCH);
        const res = await api.post<Result>(`/api/import/${kind}`, { rows: batch });
        total.imported += res.imported;
        total.skipped.push(...res.skipped.map((s) => ({ ...s, row: s.row + start + 1 })));
        setProgress(Math.min(rows.length, start + BATCH));
      }
      setResult(total);
      props.onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The import stopped because the connection failed. Rows already imported are kept; run it again and they will be skipped.");
    } finally {
      setBusy(false);
    }
  }

  const label = kind === "expenses" ? "expenses" : "sales";
  return (
    <Sheet title={`Import ${label} from a spreadsheet`} onClose={props.onClose}>
      <div className="sb-sheet-body">
        <p className="sb-help">
          Save your sheet as a CSV file. The first row must be headings:{" "}
          {kind === "expenses"
            ? "date, amount, category, description."
            : "date, description, amount, and optionally customer and payment_mode (Cash, POS, Transfer, Card, Credit)."}
          {" "}Dates are YYYY-MM-DD. Up to two years back; not in the future.
          {kind === "expenses" && " A category not on your list is added; an archived one is skipped."}
        </p>
        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}

        <div className="sb-field">
          <label htmlFor="import-file">CSV file</label>
          <input id="import-file" type="file" accept=".csv,text/csv" disabled={busy}
            onChange={(e) => void pick(e.target.files?.[0])} />
        </div>

        {rows.length > 0 && !result && (
          <>
            <p className="mt-3 text-sm text-slate-700"><strong>{fileName}</strong>: {rows.length} rows ready. Rows that are not allowed, or already recorded, are skipped with a reason.</p>
            <div className="table-wrap mt-2">
              <table aria-label="First rows of the file">
                <thead><tr>{Object.keys(rows[0]).map((h) => <th key={h}>{h}</th>)}</tr></thead>
                <tbody>
                  {rows.slice(0, 5).map((r, i) => (
                    <tr key={i}>{Object.keys(rows[0]).map((h) => <td key={h}>{r[h]}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="sb-sheet-foot">
              <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose} disabled={busy}>Cancel</button>
              <button type="button" className="sb-btn sb-btn-primary" onClick={() => void run()} disabled={busy}>
                {busy ? `Importing… ${progress} of ${rows.length}` : `Import ${rows.length} rows`}
              </button>
            </div>
          </>
        )}

        {result && (
          <div className="mt-3 text-sm">
            <p className="font-semibold text-slate-900">{result.imported} {label} imported. {result.skipped.length} skipped.</p>
            {result.skipped.length > 0 && (
              <ul className="mt-2 max-h-56 list-none overflow-y-auto text-xs text-slate-600" aria-label="Rows skipped">
                {result.skipped.map((s) => <li key={s.row}>Row {s.row}: {s.reason}</li>)}
              </ul>
            )}
            <div className="sb-sheet-foot">
              <button type="button" className="sb-btn sb-btn-primary" onClick={props.onClose}>Done</button>
            </div>
          </div>
        )}
      </div>
    </Sheet>
  );
}
