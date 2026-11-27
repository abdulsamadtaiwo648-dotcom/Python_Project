/** Budget categories at or above 80% of their limit this month, most used first. Same rules as the Budget screen. */
export interface BudgetAlert { category: string; limit: number; spent: number; percent: number }

export function budgetAlerts(
  limits: Record<string, number>,
  expenses: { category: string; amount: number; date: string }[],
  month: string,
): BudgetAlert[] {
  const spend = new Map<string, number>();
  for (const e of expenses) {
    if (e.category === "Owner's Draw (Personal)") continue;
    // The business day is the first 10 characters of the saved date; the month is its first 7.
    if (!e.date || e.date.slice(0, 7) !== month) continue;
    spend.set(e.category, (spend.get(e.category) ?? 0) + e.amount);
  }
  return Object.entries(limits)
    .filter(([key]) => key.startsWith(`${month}|`))
    .map(([key, limit]) => {
      const category = key.slice(month.length + 1);
      const spent = spend.get(category) ?? 0;
      return { category, limit, spent, percent: limit > 0 ? (spent / limit) * 100 : 0 };
    })
    .filter((a) => a.percent >= 80)
    .sort((a, b) => b.percent - a.percent);
}
