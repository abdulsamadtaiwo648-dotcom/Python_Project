import { dayOf, inRange, type Range } from "./analytics";
import type { MoneyInItem } from "./types";

/** The types of money in that are not sales. A transfer between accounts is a separate choice. */
export const MONEY_IN_KINDS = ["Owner contribution", "Loan", "Refund received", "Other income"];
export const TRANSFER_KIND = "Transfer";

/** Money in that falls inside the range, newest first. */
export function moneyInFor(items: MoneyInItem[], range: Range): MoneyInItem[] {
  return items
    .filter((i) => inRange(dayOf(i), range))
    .sort((a, b) => dayOf(b).localeCompare(dayOf(a)) || b.id - a.id);
}

/** The total of money in inside the range. */
export function moneyInTotal(items: MoneyInItem[], range: Range): number {
  return moneyInFor(items, range).reduce((sum, i) => sum + i.amount, 0);
}
