import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { lineLabel, overspentLine, periodLabel } from "./statement";

describe("statement labels", () => {
  test("a week is labelled Monday to Sunday", () => {
    assert.equal(periodLabel("week", "2026-01-12", "2026-01-18"), "12 Jan – 18 Jan 2026");
  });

  test("a month is labelled by its name and year", () => {
    assert.equal(periodLabel("month", "2026-01-01", "2026-01-31"), "January 2026");
  });

  test("a negative closing balance is reported as overspent by the amount", () => {
    assert.equal(overspentLine("5000.00"), "Overspent by ₦5,000");
    assert.equal(overspentLine("5000.50"), "Overspent by ₦5,000.50");
    assert.equal(overspentLine(null), null);
  });

  test("transfers name the other account", () => {
    assert.equal(lineLabel({ source: "transfer_in", label: "Transfer in", counterpart: "Cash", direction: "in" }), "Transfer from Cash");
    assert.equal(lineLabel({ source: "transfer_out", label: "Transfer out", counterpart: "Bank", direction: "out" }), "Transfer to Bank");
    assert.equal(lineLabel({ source: "expense", label: "Others · Taxi", counterpart: null, direction: "out" }), "Others · Taxi");
  });
});
