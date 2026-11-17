import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import Sheet from "../components/Sheet";
import { useData } from "../data";
import { money, parseSaved, relativeDay } from "../format";
import type { Expense } from "../types";

export const EXPENSE_CATEGORIES = [
  "Inventory & Materials", "Delivery & Logistics", "Fuel & Electricity",
  "Data & Airtime", "Owner's Draw (Personal)", "Others",
];

const toAmount = (v: string) => Number(v.replace(/,/g, ""));

function ExpenseForm(props: {
  initial?: Expense; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const { initial } = props;
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const n = toAmount(amount);
    if (!Number.isFinite(n) || n <= 0) return setError("Enter an amount greater than zero.");
    if (!category || !description.trim()) return setError("Choose a category and say what it was for.");
    setBusy(true);
    setError("");
    try {
      const body = { amount: n, category, description: description.trim() };
      if (initial) await api.put(`/api/expenses/${initial.server_id}`, body);
      else await api.post("/add", body);
      await props.onSaved();
      props.onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!initial || !window.confirm("Delete this expense?")) return;
    setBusy(true);
    try {
      await api.del(`/api/expenses/${initial.server_id}`);
      await props.onSaved();
      props.onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete. Try again.");
      setBusy(false);
    }
  }

  return (
    <Sheet title={initial ? "Edit expense" : "Add expense"} onClose={props.onClose} compact>
      <form onSubmit={save} className="sb-sheet-body">
        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
        <div className="sb-field">
          <label htmlFor="expense-amount">Amount</label>
          <div className="sb-money">
            <span aria-hidden="true">₦</span>
            <input id="expense-amount" type="text" inputMode="decimal" placeholder="0" required className="currency-input"
              value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
          </div>
        </div>
        <div className="sb-field">
          <label htmlFor="expense-category">Category</label>
          <select id="expense-category" required value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="" disabled>Choose a category</option>
            {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="sb-field">
          <label htmlFor="expense-description">What was it for?</label>
          <input id="expense-description" type="text" placeholder="e.g. Generator fuel" required value={description}
            onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="sb-sheet-foot">
          {initial ? (
            <>
              <button type="button" className="sb-btn sb-btn-danger-text" onClick={remove} disabled={busy}>Delete</button>
              <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose}>Cancel</button>
              <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>Save changes</button>
            </>
          ) : (
            <button type="submit" className="sb-btn sb-btn-primary sb-btn-block" disabled={busy}>{busy ? "Saving…" : "Save expense"}</button>
          )}
        </div>
      </form>
    </Sheet>
  );
}

export default function Expenses() {
  const { expenses, reload } = useData();
  const [editing, setEditing] = useState<Expense | "new" | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [exact, setExact] = useState("");

  useEffect(() => { document.title = "Expenses | SoloBiz"; }, []);

  const kpis = useMemo(() => {
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const lastStart = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const weekStart = new Date(now.getTime() - 7 * 86_400_000);
    let total = 0, last = 0, count = 0, week = 0;
    const per: Record<string, number> = {};
    for (const e of expenses) {
      const d = parseSaved(e.date);
      if (!d) continue;
      if (d >= monthStart) { total += e.amount; count++; per[e.category || "Other"] = (per[e.category || "Other"] ?? 0) + e.amount; }
      else if (d >= lastStart) last += e.amount;
      if (d >= weekStart) week++;
    }
    const top = Object.entries(per).sort((a, b) => b[1] - a[1])[0];
    const change = last > 0 ? Math.round(((total - last) / last) * 100) : null;
    return { total, count, week, top, change };
  }, [expenses]);

  const breakdown = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const e of expenses) totals[e.category || "Other"] = (totals[e.category || "Other"] ?? 0) + e.amount;
    const rows = Object.entries(totals).sort((a, b) => b[1] - a[1]);
    return { rows, grand: rows.reduce((s, [, v]) => s + v, 0) };
  }, [expenses]);

  const visible = expenses.filter((e) =>
    (!category || e.category === category) && (!exact || Math.abs(e.amount - Number(exact)) < 0.005));
  const filtered = Boolean(category || exact);
  const filterTotal = visible.reduce((s, e) => s + e.amount, 0);

  return (
    <section id="tab-expenses-content" className="tab-content page-stack" aria-labelledby="expenses-title">
      <div className="page-head">
        <div className="min-w-0"><h2 className="page-title" id="expenses-title">Expenses</h2><p className="page-sub">Where your money goes each month.</p></div>
        <button type="button" id="btn-new-expense" className="sb-btn sb-btn-primary" onClick={() => setEditing("new")}>
          <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path d="M12 5v14M5 12h14" /></svg>
          Add expense
        </button>
      </div>

      <div id="expense-kpis" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col gap-2 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Total this month</p>
          <p className="stat-value text-slate-900 truncate">{money(kpis.total)}</p>
          <p className="text-xs text-slate-500">
            {kpis.change === null ? "No expenses last month" : `${kpis.change >= 0 ? "+" : "−"}${Math.abs(kpis.change)}% vs last month`}
          </p>
        </div>
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col gap-2 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Largest category</p>
          <p className="stat-value text-slate-900 truncate">{kpis.top && kpis.total > 0 ? kpis.top[0] : "None"}</p>
          <p className="text-xs text-slate-500">
            {kpis.top && kpis.total > 0 ? `${money(kpis.top[1])} · ${Math.round((kpis.top[1] / kpis.total) * 100)}%` : "No expenses this month"}
          </p>
        </div>
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col gap-2 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Transactions</p>
          <p className="stat-value text-slate-900 truncate">{kpis.count}</p>
          <p className="text-xs text-slate-500">{kpis.week} this week</p>
        </div>
      </div>

      {filterOpen && (
        <section id="expense-filter-panel" className="sb-panel filter-panel" aria-label="Filter expenses">
          <div className="filter-grid filter-grid-2">
            <div className="sb-field">
              <label htmlFor="filter-category">Category</label>
              <select id="filter-category" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="sb-field">
              <label htmlFor="filter-amount-exact">Exact amount (₦)</label>
              <input id="filter-amount-exact" type="number" min={0} step="any" inputMode="decimal" placeholder="Any"
                value={exact} onChange={(e) => setExact(e.target.value)} />
            </div>
          </div>
          {filtered && (
            <div className="filter-result">
              <p>Filtered</p>
              <p><span>{money(filterTotal)}</span> · <span>{visible.length} result{visible.length === 1 ? "" : "s"}</span></p>
            </div>
          )}
        </section>
      )}

      <div id="expense-layout" className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 expense-list-panel">
          <div className="expense-list-head">
            <h3 className="expense-list-title">Recent expenses</h3>
            <div className="list-toolbar expense-toolbar-inline">
              <button type="button" className="sb-chip" aria-expanded={filterOpen} aria-controls="expense-filter-panel" onClick={() => setFilterOpen(!filterOpen)}>
                <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M4 6h16M7 12h10M10 18h4" /></svg>
                Filter {filtered && <span className="sb-chip-count">{[category, exact].filter(Boolean).length}</span>}
              </button>
              <p className="list-toolbar-text" aria-live="polite">{filtered ? `${visible.length} of ${expenses.length}` : ""}</p>
              {filtered && <button type="button" className="sb-link" onClick={() => { setCategory(""); setExact(""); }}>Clear</button>}
            </div>
          </div>
          <div className="sb-list-card" id="transaction-list">
            {expenses.length === 0 && <p className="list-empty">No expenses yet. Tap “Add expense” to record one.</p>}
            {visible.map((e) => (
              <div key={e.server_id} tabIndex={0} role="button" className="expense-card"
                aria-label={`Edit expense: ${e.category}, ${money(e.amount)}`}
                onClick={() => setEditing(e)} onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && setEditing(e)}>
                <div className="category-icon-val expense-icon" aria-hidden="true">{(e.category || "O")[0].toUpperCase()}</div>
                <div className="expense-text">
                  <p className="expense-category-val"><span className="category-name">{e.category || "Other"}</span></p>
                  <p className="expense-desc-val">{e.description || "No description"}</p>
                </div>
                <p className="expense-when">{relativeDay(e.date)}</p>
                <p className="expense-amount-val">{money(e.amount)}</p>
              </div>
            ))}
          </div>
          {filtered && visible.length === 0 && <p className="list-empty">No expenses match your filter.</p>}
          <p className="page-note">Tap an expense to change or delete it.</p>
        </div>

        <aside id="expense-breakdown" className="dash-panel min-w-0 self-start rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="expense-breakdown-heading">
          <h3 id="expense-breakdown-heading" className="text-base font-bold text-slate-900">By category</h3>
          <p className="mt-1 text-xs text-slate-500">Where this period’s expenses went.</p>
          <ul className="mt-4 space-y-4">
            {breakdown.grand <= 0 && <li className="text-sm text-slate-500">No expenses yet.</li>}
            {breakdown.grand > 0 && breakdown.rows.map(([name, value]) => {
              const share = Math.round((value / breakdown.grand) * 100);
              return (
                <li key={name} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="min-w-0 truncate font-medium text-slate-800">{name}</span>
                    <span className="flex-shrink-0 font-semibold text-slate-900">{money(value)} <span className="breakdown-pct">{share}%</span></span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-blue-600" style={{ width: `${share}%` }} /></div>
                </li>
              );
            })}
          </ul>
        </aside>
      </div>

      {editing && (
        <ExpenseForm initial={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={reload} />
      )}
    </section>
  );
}
