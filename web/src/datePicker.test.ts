import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { shiftIso } from "./ui/date-picker";

describe("shiftIso", () => {
  test("yesterday crosses month and year boundaries", () => {
    assert.equal(shiftIso("2026-11-27", -1), "2026-11-26");
    assert.equal(shiftIso("2027-01-01", -1), "2026-12-31");
    assert.equal(shiftIso("2026-03-01", -1), "2026-02-28");
  });

  test("leap day and forward shifts", () => {
    assert.equal(shiftIso("2028-03-01", -1), "2028-02-29");
    assert.equal(shiftIso("2026-12-31", 1), "2027-01-01");
  });
});
