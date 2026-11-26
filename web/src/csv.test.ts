import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { parseCsv, toObjects } from "./csv";

describe("reading a spreadsheet export", () => {
  test("quoted fields keep their commas, quotes and line breaks", () => {
    const text = 'date,amount,category,description\r\n2026-11-01,"1,500",Fuel & Electricity,"Gen fuel, 10L"\r\n2026-11-02,800,Others,"Said ""hi""\nthen left"\r\n';
    assert.deepEqual(parseCsv(text), [
      ["date", "amount", "category", "description"],
      ["2026-11-01", "1,500", "Fuel & Electricity", "Gen fuel, 10L"],
      ["2026-11-02", "800", "Others", 'Said "hi"\nthen left'],
    ]);
  });

  test("a byte order mark at the start is ignored", () => {
    assert.deepEqual(parseCsv("﻿date,amount\n2026-11-01,5")[0], ["date", "amount"]);
  });

  test("blank lines are skipped", () => {
    assert.equal(parseCsv("a,b\n\n1,2\n\n").length, 2);
  });
});

describe("matching columns to the import", () => {
  test("headings are matched without regard to case or spaces", () => {
    const { rows, missing } = toObjects("expenses", parseCsv("Date,Amount,Category,Description\n2026-11-01,5,Others,Tea"));
    assert.deepEqual(missing, []);
    assert.deepEqual(rows[0], { date: "2026-11-01", amount: "5", category: "Others", description: "Tea" });
  });

  test("a missing required column is reported by name", () => {
    const { missing } = toObjects("sales", parseCsv("date,amount\n2026-11-01,5"));
    assert.deepEqual(missing, ["description"]);
  });

  test("a file with only a heading has no rows", () => {
    assert.deepEqual(toObjects("expenses", parseCsv("date,amount,category,description")).rows, []);
  });
});
