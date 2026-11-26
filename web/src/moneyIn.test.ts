import { parseCsv, toObjects } from "./csv";
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { moneyInFor, moneyInTotal, MONEY_IN_KINDS } from "./moneyIn";
import type { MoneyInItem } from "./types";

const items: MoneyInItem[] = [
  { id: 1, amount: 50000, kind: "Owner contribution", description: "Restock", date: "2026-11-02 09:00 AM", entry_date: "2026-11-02" },
  { id: 2, amount: 20000, kind: "Loan", description: null, date: "2026-11-20 09:00 AM", entry_date: "2026-11-20" },
  { id: 3, amount: 7000, kind: "Refund received", description: "Supplier", date: "2026-03-09 09:00 AM", entry_date: "2026-03-09" },
  { id: 4, amount: 9999, kind: "Other income", description: null, date: "2025-11-30 09:00 AM", entry_date: "2025-11-30" },
];

describe("money in for a month or a year", () => {
  test("the month total counts only that month's business dates", () => {
    assert.equal(moneyInTotal(items, { kind: "month", ym: "2026-11" }), 70000);
  });

  test("the year total covers the whole year, and not the year before", () => {
    assert.equal(moneyInTotal(items, { kind: "year", year: "2026" }), 77000);
  });

  test("a month with nothing is zero", () => {
    assert.equal(moneyInTotal(items, { kind: "month", ym: "2026-06" }), 0);
  });

  test("entries for a month are listed newest first", () => {
    assert.deepEqual(moneyInFor(items, { kind: "month", ym: "2026-11" }).map((i) => i.id), [2, 1]);
  });

  test("the kinds match the ones the server accepts", () => {
    assert.deepEqual(MONEY_IN_KINDS, ["Owner contribution", "Loan", "Refund received", "Other income"]);
  });
});

describe("money in import columns", () => {
  test("a transfer row names both accounts", () => {
    const table = parseCsv("date,amount,type,received_into,from_account,description\n2026-01-13,3000,Transfer,Petty Cash,Cash,Top up");
    const { rows, missing } = toObjects("money_in", table);
    assert.deepEqual(missing, []);
    assert.equal(rows[0].type, "Transfer");
    assert.equal(rows[0].received_into, "Petty Cash");
    assert.equal(rows[0].from_account, "Cash");
  });

  test("a money-in file without a type column is refused by name", () => {
    const { missing } = toObjects("money_in", parseCsv("date,amount\n2026-01-13,3000"));
    assert.deepEqual(missing, ["type"]);
  });
});
