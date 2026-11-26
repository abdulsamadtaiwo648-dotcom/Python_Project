import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { isNairaAmount, openingBalanceOrZero } from "./accounts";

describe("opening balance text", () => {
  test("plain, comma-separated and negative amounts are accepted", () => {
    assert.equal(isNairaAmount("5000"), true);
    assert.equal(isNairaAmount("5,000.50"), true);
    assert.equal(isNairaAmount("-500"), true);
  });

  test("text that is not money is refused", () => {
    assert.equal(isNairaAmount("abc"), false);
    assert.equal(isNairaAmount("12.345"), false);
    assert.equal(isNairaAmount("1e3"), false);
    assert.equal(isNairaAmount("-"), false);
    assert.equal(isNairaAmount(""), false);
  });

  test("a blank opening balance is zero", () => {
    assert.equal(openingBalanceOrZero("   "), "0");
    assert.equal(openingBalanceOrZero(" 250 "), "250");
  });
});
