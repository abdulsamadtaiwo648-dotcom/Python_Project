import { ymLabel, shiftYm } from "./month";
import type { Expense, Sale } from "./types";

export type Period = "daily" | "weekly" | "monthly" | "yearly";

/** What the analysis covers: one calendar month, or one calendar year. */
export type Range = { kind: "month"; ym: string } | { kind: "year"; year: string };

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

/** A record's business day as 'YYYY-MM-DD'. Falls back to the saved date text for offline records. */
export function dayOf(r: { entry_date?: string; date: string }): string {
  return (r.entry_date || r.date || "").slice(0, 10);
}

export function inRange(day: string, range: Range): boolean {
  if (!DAY_RE.test(day)) return false;
  return range.kind === "month" ? day.startsWith(range.ym) : day.startsWith(range.year);
}

export function rangeLabel(range: Range): string {
  return range.kind === "month" ? ymLabel(range.ym) : range.year;
}

export interface Totals { value: number; collected: number; expenses: number; balance: number; net: number }

export function totalsInRange(sales: Sale[], expenses: Expense[], range: Range): Totals {
  let value = 0, collected = 0, spent = 0, balance = 0;
  for (const s of sales) {
    if (!inRange(dayOf(s), range)) continue;
    value += s.total_value;
    collected += s.amount_paid;
    balance += Math.max(0, s.total_value - s.amount_paid);
  }
  for (const e of expenses) if (inRange(dayOf(e), range)) spent += e.amount;
  return { value, collected, expenses: spent, balance, net: collected - spent };
}

const SHORT = { month: "short", day: "numeric", timeZone: "UTC" } as const;

function utcDate(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

/** The chart bucket a business day falls in: a sortable key and a short label. */
function bucketOf(day: string, period: Period): { key: string; label: string } {
  if (period === "daily") return { key: day, label: utcDate(day).toLocaleDateString("en-NG", SHORT) };
  if (period === "weekly") {
    const d = utcDate(day);
    const start = new Date(d.getTime() - d.getUTCDay() * 86400000);
    return { key: start.toISOString().slice(0, 10), label: "Wk " + start.toLocaleDateString("en-NG", SHORT) };
  }
  if (period === "monthly") {
    return { key: day.slice(0, 7), label: utcDate(day).toLocaleDateString("en-NG", { month: "short", year: "2-digit", timeZone: "UTC" }) };
  }
  return { key: day.slice(0, 4), label: day.slice(0, 4) };
}

export interface Bucket { label: string; sortDate: number; sales: number; expenses: number }

/** Sales and expenses grouped into chart buckets for a period, inside the range. */
export function chartBuckets(sales: Sale[], expenses: Expense[], period: Period, range: Range): Bucket[] {
  const map = new Map<string, Bucket>();
  const add = (record: { entry_date?: string; date: string }, series: "sales" | "expenses", amount: number) => {
    const day = dayOf(record);
    if (!inRange(day, range)) return;
    const { key, label } = bucketOf(day, period);
    let b = map.get(key);
    if (!b) {
      b = { label, sortDate: Date.parse(key) || 0, sales: 0, expenses: 0 };
      map.set(key, b);
    }
    b[series] += Number.isFinite(amount) ? amount : 0;
  };
  for (const s of sales) add(s, "sales", s.amount_paid);
  for (const e of expenses) add(e, "expenses", e.amount);
  return [...map.values()].sort((a, b) => a.sortDate - b.sortDate);
}

/** The last `count` months ending at `endYm`, each one bucket, with empty months kept as zeros. */
export function lastMonths(sales: Sale[], expenses: Expense[], endYm: string, count = 12): Bucket[] {
  const keys = Array.from({ length: count }, (_, i) => shiftYm(endYm, i - (count - 1)));
  const sums = new Map(keys.map((k) => [k, { sales: 0, expenses: 0 }]));
  for (const s of sales) { const t = sums.get(dayOf(s).slice(0, 7)); if (t) t.sales += s.amount_paid; }
  for (const e of expenses) { const t = sums.get(dayOf(e).slice(0, 7)); if (t) t.expenses += e.amount; }
  return keys.map((k) => ({
    label: bucketOf(k + "-01", "monthly").label, sortDate: Date.parse(k), ...sums.get(k)!,
  }));
}

export interface Group { label: string; sortDate: number; volume: number; items: Sale[] }

function groupLabel(day: string, period: Period): string {
  if (period === "daily") return utcDate(day).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  if (period === "weekly") {
    const d = utcDate(day);
    const start = new Date(d.getTime() - d.getUTCDay() * 86400000);
    return "Week of " + start.toLocaleDateString("en-NG", SHORT);
  }
  if (period === "monthly") return ymLabel(day.slice(0, 7));
  return day.slice(0, 4);
}

/** Sales inside the range, grouped by period, newest first. */
export function groupSales(sales: Sale[], period: Period, range: Range): Group[] {
  const groups = new Map<string, Group>();
  for (const s of sales) {
    const day = dayOf(s);
    if (!inRange(day, range)) continue;
    const label = groupLabel(day, period);
    const g = groups.get(label) ?? { label, sortDate: 0, volume: 0, items: [] };
    g.sortDate = Math.max(g.sortDate, Date.parse(day) || 0);
    g.volume += s.total_value;
    g.items.push(s);
    groups.set(label, g);
  }
  return [...groups.values()].sort((a, b) => b.sortDate - a.sortDate);
}
