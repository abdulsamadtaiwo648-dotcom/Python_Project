// Offline outbox. Changes made without a connection are kept on this device,
// shown straight away, and sent to the server later, in order. Each carries an
// id the server remembers, so a send that landed but was never confirmed is not
// applied twice.

import type { Expense, Sale } from "./types";

export type OpKind = "checkout" | "expense_add" | "expense_edit" | "expense_delete" | "payment" | "sale_delete";

export interface Op {
  id: string;
  kind: OpKind;
  method: "POST" | "PUT" | "DELETE";
  url: string;
  body?: unknown;
  at: number;
  /** What the screen should look like until the server confirms it. */
  meta: {
    sales?: Sale[];                      // checkout: rows to show
    stock?: Record<number, number>;      // product id -> units (checkout takes, sale_delete returns)
    expense?: Expense;                   // expense_add
    expenseId?: number;                  // expense_edit / expense_delete
    patch?: Partial<Expense>;            // expense_edit
    saleId?: number;                     // payment
    amount?: number;                     // payment
    checkoutId?: string | null;          // sale_delete
    saleIds?: number[];                  // sale_delete
  };
}

export interface FailedOp { id: string; kind: OpKind; message: string }

const key = (userId: string, what: "outbox" | "failed") => `solobiz:${what}:${userId}`;

function read<T>(k: string): T[] {
  try {
    return JSON.parse(localStorage.getItem(k) || "[]") as T[];
  } catch {
    return [];
  }
}
function write<T>(k: string, items: T[]) {
  try {
    localStorage.setItem(k, JSON.stringify(items));
  } catch {
    /* storage full or blocked: the queue still works for this visit */
  }
}

export const newOpId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const loadOutbox = (userId: string) => read<Op>(key(userId, "outbox"));
export const saveOutbox = (userId: string, ops: Op[]) => write(key(userId, "outbox"), ops);
export const loadFailed = (userId: string) => read<FailedOp>(key(userId, "failed"));
export const saveFailed = (userId: string, items: FailedOp[]) => write(key(userId, "failed"), items);

let tempId = -Date.now();
/** Ids below zero mark rows that exist only on this device so far. */
export const nextTempId = () => (tempId -= 1);

/** "YYYY-MM-DD hh:mm AM", the format the server stores. */
export function nowStamp(d = new Date()): string {
  const h = d.getHours() % 12 || 12;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(h)}:${p(d.getMinutes())} ${d.getHours() >= 12 ? "PM" : "AM"}`;
}
