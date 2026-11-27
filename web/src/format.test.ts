import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { compactNaira, money } from "./format";

describe("compactNaira", () => {
  test("short amounts for charts and ring totals", () => {
    assert.equal(compactNaira(36642301), "₦36.6M");
    assert.equal(compactNaira(145000), "₦145K");
    assert.equal(compactNaira(2420), "₦2.4K");
  });
});

describe("money", () => {
  test("whole and decimal amounts", () => {
    assert.equal(money(1500), "₦1,500");
    assert.equal(money(12345.67), "₦12,345.67");
    assert.equal(money(0), "₦0");
  });

  test("the minus sign goes before the naira sign", () => {
    assert.equal(money(-1500), "-₦1,500");
    assert.equal(money(-0.5), "-₦0.50");
    assert.equal(money(-2000000), "-₦2,000,000");
  });

  test("missing or invalid values read as zero", () => {
    assert.equal(money(null), "₦0");
    assert.equal(money(undefined), "₦0");
    assert.equal(money(NaN), "₦0");
  });
});
