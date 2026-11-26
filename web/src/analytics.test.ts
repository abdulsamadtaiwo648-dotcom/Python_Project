import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { chartBuckets, groupSales, lastMonths, totalsInRange } from "./analytics";
import type { Expense, Sale } from "./types";

// A business day decides the month. An offline record has no entry_date, so its date text decides.
const sales = [
  { id: 1, total_value: 1000, amount_paid: 1000, entry_date: "2026-10-31", date: "2026-10-31 11:50 PM" },
  { id: 2, total_value: 500, amount_paid: 200, entry_date: "2026-11-02", date: "2026-11-02 09:00 AM", description: "Rice", customer_name: "Ada" },
  { id: 3, total_value: 300, amount_paid: 300, date: "2026-11-03 09:00 AM", description: "Offline", customer_name: "Walk-in" },
] as unknown as Sale[];

const expenses = [
  { id: 1, amount: 400, entry_date: "2026-10-05", date: "2026-10-05 09:00 AM" },
  { id: 2, amount: 150, entry_date: "2026-11-04", date: "2026-11-04 09:00 AM" },
] as unknown as Expense[];

const nov = { kind: "month", ym: "2026-11" } as const;
const year = { kind: "year", year: "2026" } as const;

describe("totals for a range", () => {
  test("a month counts records by their business day", () => {
    assert.deepEqual(totalsInRange(sales, expenses, nov), {
      value: 800, collected: 500, moneyIn: 0, expenses: 150, balance: 300, net: 350,
    });
  });

  test("a year covers both months", () => {
    assert.deepEqual(totalsInRange(sales, expenses, year), {
      value: 1800, collected: 1500, moneyIn: 0, expenses: 550, balance: 300, net: 950,
    });
  });
});

describe("chart buckets", () => {
  test("a year groups by month", () => {
    const b = chartBuckets(sales, expenses, "monthly", year);
    assert.deepEqual(b.map((x) => [x.label, x.sales, x.expenses]), [["Oct 26", 1000, 400], ["Nov 26", 500, 150]]);
  });

  test("a month groups by day, and a day with only an expense still gets a bucket", () => {
    const d = chartBuckets(sales, expenses, "daily", nov);
    assert.deepEqual(d.map((x) => x.sales), [200, 300, 0]);
  });

  test("a month has one monthly bucket", () => {
    assert.equal(chartBuckets(sales, expenses, "monthly", nov).length, 1);
  });

  test("the last 12 months end at the month shown and keep empty months as zero", () => {
    const last = lastMonths(sales, expenses, "2026-11", 12);
    assert.equal(last.length, 12);
    assert.equal(last[0].label, "Dec 25");
    assert.equal(last[11].label, "Nov 26");
    assert.equal(last[11].sales, 500);
    assert.equal(last.find((x) => x.label === "Oct 26")?.sales, 1000);
    assert.equal(last.find((x) => x.label === "Jan 26")?.sales, 0);
  });
});

describe("sales by period", () => {
  test("a month is one group named after the month", () => {
    const g = groupSales(sales, "monthly", nov);
    assert.deepEqual(g.map((x) => [x.label, x.volume]), [["November 2026", 800]]);
  });

  test("days are newest first", () => {
    assert.deepEqual(groupSales(sales, "daily", nov).map((x) => x.label), ["3 Nov 2026", "2 Nov 2026"]);
  });
});

// --- money in ---------------------------------------------------------------------------------

import type { MoneyInItem } from "./types";

const moneyIn = [
  { id: 1, amount: 4000, kind: "Owner contribution", description: null, date: "2026-11-02 09:00 AM", entry_date: "2026-11-02" },
  { id: 2, amount: 9000, kind: "Loan", description: null, date: "2026-10-12 09:00 AM", entry_date: "2026-10-12" },
] as unknown as MoneyInItem[];

describe("money in in the analysis", () => {
  test("cash flow is sales collected plus money in minus expenses, not profit", () => {
    const t = totalsInRange(sales, expenses, nov, moneyIn);
    assert.equal(t.moneyIn, 4000);
    assert.equal(t.net, 500 + 4000 - 150);
  });

  test("the year includes money in from both months", () => {
    const t = totalsInRange(sales, expenses, year, moneyIn);
    assert.equal(t.moneyIn, 13000);
    assert.equal(t.net, 1500 + 13000 - 550);
  });

  test("without money in the totals are unchanged", () => {
    assert.equal(totalsInRange(sales, expenses, nov).net, 350);
  });

  test("each chart bucket carries money in and its own net", () => {
    const b = chartBuckets(sales, expenses, "monthly", year, moneyIn);
    assert.deepEqual(b.map((x) => [x.label, x.moneyIn, x.net]), [["Oct 26", 9000, 1000 + 9000 - 400], ["Nov 26", 4000, 500 + 4000 - 150]]);
  });

  test("a day with money in and no sale still gets a bucket", () => {
    const b = chartBuckets([], [], "daily", nov, moneyIn);
    assert.deepEqual(b.map((x) => [x.label, x.moneyIn, x.net]), [["2 Nov", 4000, 4000]]);
  });

  test("the last 12 months include money in", () => {
    const last = lastMonths(sales, expenses, "2026-11", 12, moneyIn);
    assert.equal(last[last.length - 1].moneyIn, 4000);
    assert.equal(last[last.length - 1].net, 500 + 4000 - 150);
    assert.equal(last.find((x) => x.label === "Oct 26")?.moneyIn, 9000);
  });

  test("a period with only money in appears in sales by period, with its own line", () => {
    const g = groupSales([], "monthly", nov, moneyIn);
    assert.deepEqual(g.map((x) => [x.label, x.volume, x.moneyIn, x.moneyInItems.length]), [["November 2026", 0, 4000, 1]]);
  });

  test("a period with sales and money in keeps both", () => {
    const g = groupSales(sales, "monthly", nov, moneyIn);
    assert.deepEqual(g.map((x) => [x.label, x.volume, x.moneyIn]), [["November 2026", 800, 4000]]);
  });
});
