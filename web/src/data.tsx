import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { BusinessProfile, DashboardSummary, Expense, Product, Sale } from "./types";

interface DataState {
  summary: DashboardSummary | null;
  sales: Sale[];
  expenses: Expense[];
  products: Product[];
  profile: BusinessProfile | null;
  loading: boolean;
  /** Reload everything after a write; cheap enough for a small business. */
  reload: () => Promise<void>;
}

const Ctx = createContext<DataState | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [sales, setSales] = useState<Sale[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    const [s, i, e, p, b] = await Promise.allSettled([
      api.get<DashboardSummary & { status: string }>("/api/dashboard"),
      api.get<{ income: Sale[] }>("/api/income"),
      api.get<{ expenses: Expense[] }>("/api/expenses"),
      api.get<{ presets: Product[] }>("/api/inventory-presets"),
      api.get<{ profile: BusinessProfile }>("/api/business_profile"),
    ]);
    if (s.status === "fulfilled") setSummary(s.value);
    if (i.status === "fulfilled") setSales(i.value.income);
    if (e.status === "fulfilled") setExpenses(e.value.expenses);
    if (p.status === "fulfilled") setProducts(p.value.presets);
    if (b.status === "fulfilled") setProfile(b.value.profile);
    setLoading(false);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo(
    () => ({ summary, sales, expenses, products, profile, loading, reload }),
    [summary, sales, expenses, products, profile, loading, reload],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData must be used inside DataProvider");
  return v;
}
