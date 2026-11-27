import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { formatMoneyInput, parseMoneyInput } from "./ui/money-input";

describe("formatMoneyInput", () => {
  test("groups thousands while typing", () => {
    assert.equal(formatMoneyInput("1250000"), "1,250,000");
    assert.equal(formatMoneyInput("1,250,000"), "1,250,000");
    assert.equal(formatMoneyInput("999"), "999");
  });

  test("keeps at most two decimals", () => {
    assert.equal(formatMoneyInput("1500.5"), "1,500.5");
    assert.equal(formatMoneyInput("1500.567"), "1,500.56");
  });

  test("drops letters and leading zeros", () => {
    assert.equal(formatMoneyInput("abc12x3"), "123");
    assert.equal(formatMoneyInput("0045"), "45");
    assert.equal(formatMoneyInput(""), "");
  });
});

describe("parseMoneyInput", () => {
  test("reads the typed value back as a number", () => {
    assert.equal(parseMoneyInput("1,250,000"), 1250000);
    assert.equal(parseMoneyInput("1,500.50"), 1500.5);
  });

  test("empty or partial input is not an amount", () => {
    assert.equal(parseMoneyInput(""), null);
    assert.equal(parseMoneyInput("."), null);
  });
});
