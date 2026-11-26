import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { monthNow, monthOfRecord, shiftYm, withPendingForMonth, ymLabel } from "./month";
import type { DashboardSummary } from "./types";

describe("months", () => {
  test("shifting crosses the year in both directions", () => {
    assert.equal(shiftYm("2026-01", -1), "2025-12");
    assert.equal(shiftYm("2026-12", 1), "2027-01");
    assert.equal(shiftYm("2026-11", -1), "2026-10");
  });

  test("labels read as a month and year", () => {
    assert.equal(ymLabel("2026-11"), "November 2026");
  });

  test("the current month is counted in UTC, as the server counts it", () => {
    assert.equal(monthNow(new Date("2026-11-30T23:30:00Z")), "2026-11");
    assert.equal(monthNow(new Date("2026-12-01T00:30:00Z")), "2026-12");
  });

  test("a record belongs to its business day, falling back to its saved date", () => {
    assert.equal(monthOfRecord({ entry_date: "2026-10-31", date: "2026-11-01 01:00 AM" }), "2026-10");
    assert.equal(monthOfRecord({ date: "2026-11-02 09:00 AM" }), "2026-11");
  });
});

describe("changes not yet synced", () => {
  const base = {
    month_income: 1000, month_expenses: 200, month_net: 800, selected_month: "2026-11",
    cash: { month: "2026-11", sales_collected: 1000, money_in: 4000, expenses: 200, profit: 800, cash_balance: 4800 },
  } as unknown as DashboardSummary;

  const ops = [
    { kind: "checkout", meta: { sales: [
      { date: "2026-11-05 10:00 AM", amount_paid: 500 },
      { date: "2026-10-05 10:00 AM", amount_paid: 9999 },
    ] } },
    { kind: "expense_add", meta: { expense: { date: "2026-11-06 10:00 AM", amount: 300 } } },
    { kind: "expense_add", meta: { expense: { date: "2026-10-06 10:00 AM", amount: 7777 } } },
  ] as never;

  test("only changes dated in the month shown are added", () => {
    const r = withPendingForMonth(base, ops, "2026-11");
    assert.equal(r.month_income, 1500);
    assert.equal(r.month_expenses, 500);
    assert.equal(r.month_net, 1000);
  });

  test("the cash card follows, and money in is left alone", () => {
    const r = withPendingForMonth(base, ops, "2026-11");
    assert.deepEqual(r.cash, {
      month: "2026-11", sales_collected: 1500, money_in: 4000, expenses: 500, profit: 1000, cash_balance: 5000,
    });
  });

  test("with nothing pending the figures are unchanged", () => {
    const r = withPendingForMonth(base, [], "2026-11");
    assert.equal(r.month_income, 1000);
    assert.deepEqual(r.cash, base.cash);
  });
});
