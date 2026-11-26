import type { Op } from "./offline";
import type { DashboardSummary } from "./types";

export const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const REMEMBER_KEY = "solobiz.dashboard.month";

/** The current month as the server counts it (UTC), 'YYYY-MM'. */
export function monthNow(d = new Date()): string {
  return d.toISOString().slice(0, 7);
}

/** Move a 'YYYY-MM' month by whole months. */
export function shiftYm(ym: string, delta: number): string {
  const [y, m] = ym.split("-").map(Number);
  const index = y * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** 'November 2026' */
export function ymLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-NG", { month: "long", year: "numeric", timeZone: "UTC" });
}

/** The month a record belongs to: its business date, falling back to its saved date text. */
export function monthOfRecord(r: { entry_date?: string; date: string }): string {
  return (r.entry_date || r.date || "").slice(0, 7);
}

/** The month picked earlier this session, or null. A per-browser convenience only. */
export function readRemembered(): string | null {
  try {
    const value = sessionStorage.getItem(REMEMBER_KEY);
    return value && MONTH_RE.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function remember(ym: string): void {
  try {
    sessionStorage.setItem(REMEMBER_KEY, ym);
  } catch {
    /* storage unavailable: the choice lasts for this visit only */
  }
}

/**
 * Adds changes saved on this device that the server has not confirmed yet to the figures of the
 * month shown. Only changes dated in that month count.
 */
export function withPendingForMonth(s: DashboardSummary, ops: Op[], ym: string): DashboardSummary {
  let income = s.month_income, spend = s.month_expenses;
  for (const op of ops) {
    if (op.kind === "checkout") {
      for (const sale of op.meta.sales ?? []) if (monthOfRecord(sale) === ym) income += sale.amount_paid;
    }
    if (op.kind === "expense_add" && op.meta.expense && monthOfRecord(op.meta.expense) === ym) {
      spend += op.meta.expense.amount;
    }
  }
  return { ...s, month_income: income, month_expenses: spend, month_net: income - spend };
}
