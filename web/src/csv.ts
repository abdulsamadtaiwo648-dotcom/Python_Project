/** Reads a CSV spreadsheet export and turns its rows into objects keyed by header. */

export type ImportKind = "expenses" | "sales";

export const COLUMNS: Record<ImportKind, { required: string[]; optional: string[] }> = {
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

