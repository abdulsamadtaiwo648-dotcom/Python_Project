import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api, isNetworkError, loadSession } from "./api";
import {
  loadFailed, loadOutbox, newOpId, recoverOutbox, requestDurableStorage, saveFailed, saveOutbox, type FailedOp, type Op,
} from "./offline";
import { parseSaved } from "./format";
import { useSession } from "./session";
import type { AccountView, BusinessProfile, DashboardSummary, Expense, FeatureKey, MoneyInItem, Product, Sale, Subscription } from "./types";

type NewOp = Omit<Op, "id" | "at">;

interface DataState {
  summary: DashboardSummary | null;
  sales: Sale[];
  expenses: Expense[];
  /** Money in that is not a sale. */
  moneyIn: MoneyInItem[];
  /** The business's accounts, including archived ones. */
  accounts: AccountView[];
  products: Product[];
  profile: BusinessProfile | null;
  subscription: Subscription | null;
  /** Does the current plan include this feature? (true until the plan is known) */
  can: (feature: FeatureKey) => boolean;
  loading: boolean;
  /** Changes saved on this device that the server has not confirmed yet. */
  pending: number;
  /** The same changes, for adding to a month's figures before the server confirms them. */
  pendingOps: Op[];
  failed: FailedOp[];
  dismissFailed: () => void;
  online: boolean;
  syncNow: () => Promise<void>;
  /** Reload everything from the server (no-op while offline). */
  reload: () => Promise<void>;
  /**
   * Send a change. Online it goes straight to the server; offline (or while
   * earlier changes are still waiting) it is queued and shown right away.
   * Resolves { queued } and throws only when the server rejects it.
   */
  write: (op: NewOp) => Promise<{ queued: boolean }>;
}

const Ctx = createContext<DataState | null>(null);

/** Failures that say nothing about the change itself, so it must not be thrown away. */
const isRetryable = (e: ApiError) =>
  e.status === 401 || e.status === 408 || e.status === 429 || e.status >= 500 ||
  (e.status === 400 && /token/i.test(e.message));

const monthOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
const dayOf = (d: Date) => `${monthOf(d)}-${String(d.getDate()).padStart(2, "0")}`;

/** The server's records with the not-yet-synced changes laid over them. */
function overlay(base: { sales: Sale[]; expenses: Expense[]; products: Product[] }, ops: Op[]) {
  let sales = [...base.sales];
  let expenses = [...base.expenses];
  const stock = new Map<number, number>();
  const bump = (id: number, by: number) => stock.set(id, (stock.get(id) ?? 0) + by);
  for (const op of ops) {
    const m = op.meta;
    if (op.kind === "checkout") {
      sales = [...(m.sales ?? []).map((s) => ({ ...s, pending: true })), ...sales];
      for (const [id, units] of Object.entries(m.stock ?? {})) bump(Number(id), -units);
    } else if (op.kind === "expense_add" && m.expense) {
      expenses = [{ ...m.expense, synced: false }, ...expenses];
    } else if (op.kind === "expense_edit") {
      expenses = expenses.map((e) => (e.server_id === m.expenseId ? { ...e, ...m.patch, synced: false } : e));
    } else if (op.kind === "expense_delete") {
      expenses = expenses.filter((e) => e.server_id !== m.expenseId);
    } else if (op.kind === "payment") {
      sales = sales.map((s) =>
        s.id === m.saleId
          ? { ...s, amount_paid: Math.min(s.total_value, s.amount_paid + (m.amount ?? 0)), balance_owed: Math.max(0, s.total_value - s.amount_paid - (m.amount ?? 0)), pending: true }
          : s);
    } else if (op.kind === "sale_delete") {
      const ids = new Set(m.saleIds ?? []);
      sales = sales.filter((s) => !ids.has(s.id) && !(m.checkoutId && s.checkout_id === m.checkoutId));
      for (const [id, units] of Object.entries(m.stock ?? {})) bump(Number(id), units);
    }
  }
  const products = base.products.map((p) => (stock.has(p.id) && p.track_stock ? { ...p, stock: Math.max(0, p.stock + (stock.get(p.id) ?? 0)) } : p));
  return { sales, expenses, products };
}

function adjustSummary(base: DashboardSummary | null, ops: Op[], products: Product[]): DashboardSummary | null {
  if (!base) return null;
  const now = new Date();
  const month = monthOf(now), today = dayOf(now);
  const s = { ...base };
  const add = (date: string, income: number, spend: number) => {
    const d = parseSaved(date);
    if (!d) return;
    if (monthOf(d) === month) { s.month_income += income; s.month_expenses += spend; }
    if (dayOf(d) === today) { s.today_collected += income; s.today_expenses += spend; }
    s.total_sales += income;
    s.total_expenses += spend;
  };
  for (const op of ops) {
    if (op.kind === "checkout") for (const sale of op.meta.sales ?? []) add(sale.date, sale.amount_paid, 0);
    if (op.kind === "expense_add" && op.meta.expense) add(op.meta.expense.date, 0, op.meta.expense.amount);
  }
  s.month_net = s.month_income - s.month_expenses;
  s.net_profit = s.total_sales - s.total_expenses;
  s.today_net = s.today_collected - s.today_expenses;
  s.low_stock_items = products
    .filter((p) => p.track_stock && p.stock <= (Number.isInteger(p.low_stock_threshold) ? p.low_stock_threshold : 3))
    .sort((a, b) => a.stock - b.stock)
    .map((p) => ({ item_name: p.item_name, stock: p.stock, threshold: p.low_stock_threshold }));
  return s;
}

export function DataProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const userId = user?.id ?? "anon";
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [rawSales, setSales] = useState<Sale[]>([]);
  const [rawExpenses, setExpenses] = useState<Expense[]>([]);
  const [moneyIn, setMoneyIn] = useState<MoneyInItem[]>([]);
  const [accounts, setAccounts] = useState<AccountView[]>([]);
  const [rawProducts, setProducts] = useState<Product[]>([]);
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [outbox, setOutbox] = useState<Op[]>(() => loadOutbox(userId));
  const [failed, setFailed] = useState<FailedOp[]>(() => loadFailed(userId));
  const [online, setOnline] = useState(navigator.onLine);
  const flushing = useRef(false);
  const subscriptionRef = useRef<Subscription | null>(null);
  subscriptionRef.current = subscription;
  const outboxRef = useRef(outbox);
  outboxRef.current = outbox;

  const commit = useCallback((ops: Op[]) => {
    outboxRef.current = ops;
    setOutbox(ops);
    saveOutbox(userId, ops);
  }, [userId]);

  const reload = useCallback(async () => {
    const [s, i, e, p, b, sub, mi, acct] = await Promise.allSettled([
      api.get<DashboardSummary & { status: string }>("/api/dashboard"),
      api.get<{ income: Sale[] }>("/api/income"),
      api.get<{ expenses: Expense[] }>("/api/expenses"),
      api.get<{ presets: Product[] }>("/api/inventory-presets"),
      api.get<{ profile: BusinessProfile }>("/api/business_profile"),
      api.get<Subscription & { status: string }>("/api/subscription"),
      api.get<{ money_in: MoneyInItem[] }>("/api/money-in"),
      api.get<{ accounts: AccountView[] }>("/api/accounts"),
    ]);
    if (mi.status === "fulfilled") setMoneyIn(mi.value.money_in);
    if (acct.status === "fulfilled") setAccounts(acct.value.accounts);
    if (s.status === "fulfilled") setSummary(s.value);
    if (i.status === "fulfilled") setSales(i.value.income);
    if (e.status === "fulfilled") setExpenses(e.value.expenses);
    if (p.status === "fulfilled") setProducts(p.value.presets);
    if (b.status === "fulfilled") setProfile(b.value.profile);
    if (sub.status === "fulfilled") setSubscription(sub.value);
    setLoading(false);
  }, []);

  /** Send waiting changes in order; stop at the first one the network drops. */
  const syncNow = useCallback(async () => {
    if (flushing.current || !navigator.onLine || outboxRef.current.length === 0) return;
    flushing.current = true;
    let sent = 0;
    try {
      while (outboxRef.current.length) {
        const op = outboxRef.current[0];
        try {
          await api.send(op.method, op.url, op.body, op.id);
          sent++;
        } catch (err) {
          if (isNetworkError(err)) break;
          // Signed out, token out of date, busy or down: the change is fine, keep it and try again later.
          if (err instanceof ApiError && isRetryable(err)) {
            if (err.status === 400) await loadSession().catch(() => undefined);
            break;
          }
          const message = err instanceof ApiError ? err.message : "Could not be saved.";
          const next = [...loadFailed(userId), { id: op.id, kind: op.kind, message }];
          saveFailed(userId, next);
          setFailed(next);
        }
        commit(outboxRef.current.slice(1));
      }
    } finally {
      flushing.current = false;
    }
    if (sent || outboxRef.current.length === 0) await reload();
  }, [commit, reload, userId]);

  const write = useCallback(async (input: NewOp): Promise<{ queued: boolean }> => {
    const op: Op = { ...input, id: newOpId(), at: Date.now() };
    const m = op.meta;
    const list = outboxRef.current;

    // A change to something that only exists on this device edits the waiting change itself.
    if (op.kind === "expense_edit" && (m.expenseId ?? 0) < 0) {
      commit(list.map((o) => (o.kind === "expense_add" && o.meta.expense?.server_id === m.expenseId
        ? { ...o, body: op.body, meta: { ...o.meta, expense: { ...o.meta.expense!, ...m.patch } as Expense } } : o)));
      return { queued: true };
    }
    if (op.kind === "expense_delete" && (m.expenseId ?? 0) < 0) {
      commit(list.filter((o) => !(o.kind === "expense_add" && o.meta.expense?.server_id === m.expenseId)));
      return { queued: true };
    }
    if (op.kind === "sale_delete" && (m.saleIds ?? []).some((id) => id < 0)) {
      const gone = new Set(m.saleIds);
      commit(list.filter((o) => !(o.kind === "checkout" && o.meta.sales?.some((s) => gone.has(s.id)))));
      return { queued: true };
    }

    if (op.kind === "payment" && (m.saleId ?? 0) < 0) {
      // The sale itself is still waiting: add the payment to that waiting sale.
      commit(list.map((o) => {
        const rows = o.meta.sales;
        if (o.kind !== "checkout" || !rows?.some((s) => s.id === m.saleId)) return o;
        const next = rows.map((s) => s.id === m.saleId
          ? { ...s, amount_paid: Math.min(s.total_value, s.amount_paid + (m.amount ?? 0)) } : s)
          .map((s) => ({ ...s, balance_owed: Math.max(0, s.total_value - s.amount_paid) }));
        const paid = next.reduce((n, s) => n + s.amount_paid, 0);
        return { ...o, body: { ...(o.body as object), amount_paid: paid }, meta: { ...o.meta, sales: next } };
      }));
      return { queued: true };
    }

    if (navigator.onLine && list.length === 0) {
      try {
        await api.send(op.method, op.url, op.body, op.id);
        await reload();
        return { queued: false };
      } catch (err) {
        if (!isNetworkError(err)) throw err;      // the server said no: show it
      }
    }
    // Saving on the device for later is a paid feature (Basic and Pro).
    if (subscriptionRef.current && !subscriptionRef.current.current.features.includes("offline")) {
      throw new ApiError("Recording without internet is part of the Basic and Pro plans. Connect to save this, or choose a plan.", 403, { code: "upgrade_required", feature: "offline" });
    }
    commit([...outboxRef.current, op]);
    void syncNow();
    return { queued: true };
  }, [commit, reload, syncNow]);

  // Start, and whenever the connection changes.
  useEffect(() => {
    void requestDurableStorage();
    void recoverOutbox(userId, outboxRef.current).then((lost) => {
      if (lost.length) commit([...outboxRef.current, ...lost].sort((a, b) => a.at - b.at));
    });
    void (async () => {
      await reload();
      await syncNow();
    })();
    const up = () => { setOnline(true); void syncNow(); };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    const timer = window.setInterval(() => void syncNow(), 20_000);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
      window.clearInterval(timer);
    };
  }, [reload, syncNow, commit, userId]);

  const view = useMemo(() => overlay({ sales: rawSales, expenses: rawExpenses, products: rawProducts }, outbox), [rawSales, rawExpenses, rawProducts, outbox]);
  const shownSummary = useMemo(() => adjustSummary(summary, outbox, view.products), [summary, outbox, view.products]);

  const value = useMemo<DataState>(() => ({
    summary: shownSummary, sales: view.sales, expenses: view.expenses, moneyIn, accounts, products: view.products, profile, loading, subscription,
    can: (feature) => !subscription || subscription.current.features.includes(feature),
    pending: outbox.length, pendingOps: outbox, failed, online, syncNow, reload, write,
    dismissFailed: () => { saveFailed(userId, []); setFailed([]); },
  }), [shownSummary, view, moneyIn, accounts, profile, loading, subscription, outbox, outbox.length, failed, online, syncNow, reload, write, userId]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData must be used inside DataProvider");
  return v;
}
