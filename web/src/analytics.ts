import { ymLabel, shiftYm } from "./month";
import type { Expense, MoneyInItem, Sale } from "./types";

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

/**
 * Sales collected plus money in, minus expenses. Profit (sales minus expenses) is not used here:
 * money in is cash, not a sale, so it counts in cash flow but not in profit.
 */
export interface Totals {
  value: number;
  collected: number;
  moneyIn: number;
  expenses: number;
  balance: number;
  net: number;
}

export function totalsInRange(sales: Sale[], expenses: Expense[], range: Range, moneyIn: MoneyInItem[] = []): Totals {
  let value = 0, collected = 0, spent = 0, balance = 0, received = 0;
  for (const s of sales) {
    if (!inRange(dayOf(s), range)) continue;
    value += s.total_value;
    collected += s.amount_paid;
    balance += Math.max(0, s.total_value - s.amount_paid);
  }
  for (const e of expenses) if (inRange(dayOf(e), range)) spent += e.amount;
  for (const m of moneyIn) if (inRange(dayOf(m), range)) received += m.amount;
  return { value, collected, moneyIn: received, expenses: spent, balance, net: collected + received - spent };
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

export interface Bucket {
  label: string;
  sortDate: number;
  sales: number;
  moneyIn: number;
  expenses: number;
  /** Sales collected + money in − expenses for this bucket. */
  net: number;
}

function emptyBucket(label: string, sortDate: number): Bucket {
  return { label, sortDate, sales: 0, moneyIn: 0, expenses: 0, net: 0 };
}

/** Sales, money in and expenses grouped into chart buckets for a period, inside the range. */
export function chartBuckets(sales: Sale[], expenses: Expense[], period: Period, range: Range, moneyIn: MoneyInItem[] = []): Bucket[] {
  const map = new Map<string, Bucket>();
  const add = (record: { entry_date?: string; date: string }, series: "sales" | "expenses" | "moneyIn", amount: number) => {
    const day = dayOf(record);
    if (!inRange(day, range)) return;
    const { key, label } = bucketOf(day, period);
    let b = map.get(key);
    if (!b) {
      b = emptyBucket(label, Date.parse(key) || 0);
      map.set(key, b);
    }
    b[series] += Number.isFinite(amount) ? amount : 0;
  };
  for (const s of sales) add(s, "sales", s.amount_paid);
  for (const e of expenses) add(e, "expenses", e.amount);
  for (const m of moneyIn) add(m, "moneyIn", m.amount);
  const buckets = [...map.values()].sort((a, b) => a.sortDate - b.sortDate);
  for (const b of buckets) b.net = b.sales + b.moneyIn - b.expenses;
  return buckets;
}

/** The last `count` months ending at `endYm`, each one bucket, with empty months kept as zeros. */
export function lastMonths(sales: Sale[], expenses: Expense[], endYm: string, count = 12, moneyIn: MoneyInItem[] = []): Bucket[] {
  const keys = Array.from({ length: count }, (_, i) => shiftYm(endYm, i - (count - 1)));
  const buckets = new Map(keys.map((k) => [k, emptyBucket(bucketOf(k + "-01", "monthly").label, Date.parse(k))]));
  for (const s of sales) { const b = buckets.get(dayOf(s).slice(0, 7)); if (b) b.sales += s.amount_paid; }
  for (const e of expenses) { const b = buckets.get(dayOf(e).slice(0, 7)); if (b) b.expenses += e.amount; }
  for (const m of moneyIn) { const b = buckets.get(dayOf(m).slice(0, 7)); if (b) b.moneyIn += m.amount; }
  return keys.map((k) => {
    const b = buckets.get(k)!;
    return { ...b, net: b.sales + b.moneyIn - b.expenses };
  });
}

export interface Group {
  label: string;
  sortDate: number;
  /** Sales value in this period. */
  volume: number;
  /** Money in received in this period. */
  moneyIn: number;
  items: Sale[];
  moneyInItems: MoneyInItem[];
}

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

/** Sales and money in inside the range, grouped by period, newest first. A period with only money in is kept. */
export function groupSales(sales: Sale[], period: Period, range: Range, moneyIn: MoneyInItem[] = []): Group[] {
  const groups = new Map<string, Group>();
  const groupFor = (day: string) => {
    const label = groupLabel(day, period);
    let g = groups.get(label);
    if (!g) {
      g = { label, sortDate: 0, volume: 0, moneyIn: 0, items: [], moneyInItems: [] };
      groups.set(label, g);
    }
    g.sortDate = Math.max(g.sortDate, Date.parse(day) || 0);
    return g;
  };
  for (const s of sales) {
    const day = dayOf(s);
    if (!inRange(day, range)) continue;
    const g = groupFor(day);
    g.volume += s.total_value;
    g.items.push(s);
  }
  for (const m of moneyIn) {
    const day = dayOf(m);
    if (!inRange(day, range)) continue;
    const g = groupFor(day);
    g.moneyIn += m.amount;
    g.moneyInItems.push(m);
  }
  return [...groups.values()].sort((a, b) => b.sortDate - a.sortDate);
}

export interface Slice { label: string; value: number }

/**
 * Expenses inside the range, split by category or by account, largest first. Amounts are summed in
 * kobo so the parts always add up to the total exactly.
 */
export function expenseSlices(expenses: Expense[], range: Range, by: "category" | "account", accountName: (id: number | null | undefined) => string): Slice[] {
  const totals = new Map<string, number>();
  for (const e of expenses) {
    if (!inRange(dayOf(e), range)) continue;
    const label = by === "category" ? (e.category || "Other") : (accountName(e.account_id) || "Unassigned");
    totals.set(label, (totals.get(label) ?? 0) + Math.round(e.amount * 100));
  }
  return [...totals.entries()]
    .map(([label, kobo]) => ({ label, value: kobo / 100 }))
    .sort((a, b) => b.value - a.value);
}
