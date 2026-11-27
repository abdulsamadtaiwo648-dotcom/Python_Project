import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { budgetAlerts } from "./budgetAlerts";

const expense = (category: string, amount: number, date = "2026-11-10") => ({ category, amount, date });

describe("budgetAlerts", () => {
  test("flags categories at 80% or more of their limit, most used first", () => {
    const alerts = budgetAlerts({ "2026-11|Fabric": 10000, "2026-11|Rent": 5000 }, [expense("Fabric", 9200), expense("Rent", 3000)], "2026-11");
    assert.deepEqual(alerts.map((a) => a.category), ["Fabric"]);
    assert.equal(Math.round(alerts[0].percent), 92);
  });

  test("80% exactly is flagged; just under is not", () => {
    assert.equal(budgetAlerts({ "2026-11|A": 1000 }, [expense("A", 800)], "2026-11").length, 1);
    assert.equal(budgetAlerts({ "2026-11|A": 1000 }, [expense("A", 799)], "2026-11").length, 0);
  });

  test("only this month's expenses count, and the personal draw is ignored", () => {
    const alerts = budgetAlerts({ "2026-11|A": 1000 }, [expense("A", 900, "2026-10-30"), expense("A", 500, "2026-11-02")], "2026-11");
    assert.equal(alerts.length, 0);
    assert.equal(budgetAlerts({ "2026-11|Owner's Draw (Personal)": 100 }, [expense("Owner's Draw (Personal)", 500)], "2026-11").length, 0);
  });

  test("over the limit is flagged with more than 100%", () => {
    const [alert] = budgetAlerts({ "2026-11|A": 1000 }, [expense("A", 1500)], "2026-11");
    assert.equal(alert.percent, 150);
  });
});
