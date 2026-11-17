import { parseSaved } from "./format";
import type { Expense, Sale } from "./types";

export type Period = "daily" | "weekly" | "monthly" | "yearly";

export const PERIOD_PHRASE: Record<Period, string> = {
  daily: "today", weekly: "this week", monthly: "this month", yearly: "this year",
};

const key = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Is this record's date inside the current day / week / month / year? */
export function inCurrentPeriod(value: string, period: Period, now = new Date()): boolean {
  const d = parseSaved(value);
  if (!d) return false;
  const k = key(d), today = key(now);
  if (k > today) return false;
  if (period === "daily") return k === today;
  if (period === "weekly") return k >= key(new Date(now.getFullYear(), now.getMonth(), now.getDate() - now.getDay()));
  if (period === "yearly") return k.slice(0, 4) === today.slice(0, 4);
  return k.slice(0, 7) === today.slice(0, 7);
}

export interface Totals { value: number; collected: number; expenses: number; balance: number; net: number }

export function totalsFor(sales: Sale[], expenses: Expense[], period: Period): Totals {
  let value = 0, collected = 0, spent = 0, balance = 0;
  for (const s of sales) {
    if (!inCurrentPeriod(s.date, period)) continue;
    value += s.total_value;
    collected += s.amount_paid;
    balance += Math.max(0, s.total_value - s.amount_paid);
  }
  for (const e of expenses) if (inCurrentPeriod(e.date, period)) spent += e.amount;
  return { value, collected, expenses: spent, balance, net: collected - spent };
}

export interface Bucket { label: string; sortDate: number; sales: number; expenses: number }

export function chartBuckets(sales: Sale[], expenses: Expense[], period: Period): Bucket[] {
  const map = new Map<string, Bucket>();
  const add = (value: string, series: "sales" | "expenses", amount: number) => {
    const d = parseSaved(value);
    if (!d) return;
    const b = new Date(d);
    if (period === "weekly") b.setDate(b.getDate() - b.getDay());
    else if (period === "monthly") b.setDate(1);
    else if (period === "yearly") b.setMonth(0, 1);
    b.setHours(0, 0, 0, 0);
    const k = key(b);
    if (!map.has(k)) {
      const opts: Intl.DateTimeFormatOptions =
        period === "yearly" ? { year: "numeric" } : period === "monthly" ? { month: "short", year: "2-digit" } : { month: "short", day: "numeric" };
      const text = b.toLocaleDateString("en-NG", opts);
      map.set(k, { label: period === "weekly" ? `Wk ${text}` : text, sortDate: b.getTime(), sales: 0, expenses: 0 });
    }
    map.get(k)![series] += Number.isFinite(amount) ? amount : 0;
  };
  for (const s of sales) add(s.date, "sales", s.amount_paid);
  for (const e of expenses) add(e.date, "expenses", e.amount);
  return [...map.values()].sort((a, b) => a.sortDate - b.sortDate);
}

export interface Group { label: string; sortDate: number; volume: number; items: Sale[] }

export function groupSales(sales: Sale[], period: Period): Group[] {
  const groups = new Map<string, Group>();
  for (const s of sales) {
    const d = parseSaved(s.date);
    if (!d) continue;
    let label: string;
    if (period === "daily") label = d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
    else if (period === "weekly") {
      const start = new Date(d.getFullYear(), d.getMonth(), d.getDate() - d.getDay());
      label = "Week of " + start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    } else if (period === "monthly") label = d.toLocaleDateString("en-US", { year: "numeric", month: "long" });
    else label = String(d.getFullYear());
    const g = groups.get(label) ?? { label, sortDate: 0, volume: 0, items: [] };
    g.sortDate = Math.max(g.sortDate, d.getTime());
    g.volume += s.total_value;
    g.items.push(s);
    groups.set(label, g);
  }
  return [...groups.values()].sort((a, b) => b.sortDate - a.sortDate);
}
