import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export interface ExpenseCategory {
  id: number;
  name: string;
  archived: boolean;
}

/** Used only if the list cannot be loaded (for example, offline before it was ever fetched). */
export const DEFAULT_CATEGORIES = [
  "Inventory & Materials", "Delivery & Logistics", "Fuel & Electricity",
  "Data & Airtime", "Owner's Draw (Personal)", "Others",
];

/** This business's expense categories. `active` are the ones a new expense may use. */
export function useExpenseCategories() {
  const [all, setAll] = useState<ExpenseCategory[]>(() => DEFAULT_CATEGORIES.map((name, i) => ({ id: -i - 1, name, archived: false })));
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    try {
      const res = await api.get<{ categories: ExpenseCategory[] }>("/api/expense-categories");
      setAll(res.categories);
      setLoaded(true);
    } catch {
      /* keep what we have */
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  const active = all.filter((c) => !c.archived).map((c) => c.name);
  return { all, active, loaded, reload };
}
