import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useData } from "../data";
import { money, parseSaved } from "../format";
import { useSession } from "../session";
import { useExpenseCategories } from "../categories";

// Budgets live on this device (like the earlier version), one set per account.
type Limits = Record<string, number>; // "YYYY-MM|Category" -> amount

const cur = money;
const thisMonth = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
};

function useLimits(userId: string) {
  const storageKey = `solobiz:budgets:${userId}`;
  const [limits, setLimits] = useState<Limits>(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "{}") as Limits;
    } catch {
      return {};
    }
  });
  const save = (next: Limits) => {
    setLimits(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      /* storage unavailable: keep it in memory for this visit */
    }
  };
  return [limits, save] as const;
}

export default function Budget() {
  const { user } = useSession();
  const { expenses } = useData();
  const cats = useExpenseCategories();
  const [limits, saveLimits] = useLimits(user?.id ?? "anon");
  const [month, setMonth] = useState(thisMonth());
  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { document.title = "Budget | SoloBiz"; }, []);

  const progress = useMemo(() => {
    const [y, m] = month.split("-").map(Number);
    const start = new Date(y, m - 1, 1), end = new Date(y, m, 1);
    const spend = new Map<string, number>();
    for (const e of expenses) {
      if (e.category === "Owner's Draw (Personal)") continue;
      const d = parseSaved(e.date);
      if (!d || d < start || d >= end) continue;
      spend.set(e.category, (spend.get(e.category) ?? 0) + e.amount);
    }
    return Object.entries(limits)
      .filter(([k]) => k.startsWith(`${month}|`))
      .map(([k, limit]) => {
        const cat = k.slice(month.length + 1);
        const spent = spend.get(cat) ?? 0;
        return { category: cat, limit, spent, percent: limit > 0 ? (spent / limit) * 100 : 0 };
      })
      .sort((a, b) => b.percent - a.percent);
  }, [limits, expenses, month]);

  const totalLimit = progress.reduce((n, p) => n + p.limit, 0);
  const totalSpent = progress.reduce((n, p) => n + p.spent, 0);
  const totalPct = totalLimit > 0 ? (totalSpent / totalLimit) * 100 : 0;
  const totalOver = totalSpent > totalLimit, totalNear = !totalOver && totalPct >= 80;
  const overCount = progress.filter((p) => p.spent > p.limit).length;
  const top = progress[0];
  const now = new Date();
  const [sy, sm] = month.split("-").map(Number);
  const daysLeft = now.getFullYear() === sy && now.getMonth() + 1 === sm ? new Date(sy, sm, 0).getDate() - now.getDate() : 0;

  function save(e: FormEvent) {
    e.preventDefault();
    const n = Number(amount);
    if (!category) return setError("Select a category.");
    if (!Number.isFinite(n) || n <= 0) return setError("Enter a limit greater than zero.");
    setError("");
    saveLimits({ ...limits, [`${month}|${category}`]: n });
    setAmount("");
  }

  const tone = (over: boolean, near: boolean, a: string, b: string, c: string) => (over ? a : near ? b : c);

  return (
    <section id="tab-budget-content" className="tab-content page-stack" aria-labelledby="budget-heading">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="budget-heading">Budget</h2>
          <p className="page-sub">Plan each month and track what is left.</p>
        </div>
        <div className="budget-head-actions">
          <label className="budget-month-pick">
            <span className="sr-only">Month</span>
            <input id="budget-month" type="month" aria-label="Budget month" value={month} onChange={(e) => setMonth(e.target.value || thisMonth())} />
          </label>
          <button type="button" className="sb-btn sb-btn-primary" onClick={() => document.getElementById("budget-category")?.focus()}>Set budget</button>
        </div>
      </div>

      <div id="budget-kpis" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Monthly budget</p>
          <p className="stat-value mt-2 text-2xl text-slate-900">{cur(totalLimit)}</p>
          <p className="mt-1 text-xs text-slate-500">For this month</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Spent so far</p>
          <p className="stat-value mt-2 text-2xl text-slate-900">{cur(totalSpent)}</p>
          <p className="mt-1 text-xs text-slate-500">{Math.round(totalPct)}% used</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Remaining</p>
          <p className="stat-value mt-2 text-2xl text-blue-700">{cur(Math.max(0, totalLimit - totalSpent))}</p>
          <p className="mt-1 text-xs text-slate-500">{progress.length && daysLeft > 0 ? `${daysLeft} days left` : ""}</p>
        </div>
      </div>

      <div id="budget-summary-card" className="sb-panel">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="budget-summary-title">{progress.length ? `${cur(totalSpent)} spent of ${cur(totalLimit)}` : "No budget limits set"}</p>
            <p className="sb-help">
              {!progress.length ? "Set category limits to track spending here."
                : overCount ? `${overCount} ${overCount === 1 ? "category is" : "categories are"} over limit · ${top.category} is closest at ${Math.round(top.percent)}%`
                : `${progress.length} ${progress.length === 1 ? "category" : "categories"} · ${top.category} is closest at ${Math.round(top.percent)}%`}
            </p>
          </div>
          <span className={`budget-percent shrink-0 rounded-full bg-white px-2.5 py-1 text-xs font-bold ${tone(totalOver, totalNear, "text-rose-700", "text-amber-700", "text-slate-600")}`}>{Math.round(totalPct)}%</span>
        </div>
        <div className="budget-track" role="progressbar" aria-label="Monthly budget used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(100, Math.round(totalPct))}>
          <div className={`h-full rounded-full ${tone(totalOver, totalNear, "bg-rose-500", "bg-amber-500", "bg-blue-700")}`} style={{ width: `${Math.min(100, totalPct)}%` }} />
        </div>
      </div>

      <div id="budget-categories-panel" className="budget-categories-panel">
        <h3 className="budget-categories-title">Categories</h3>
        <div id="budget-progress-list" className="budget-list" aria-live="polite">
          {progress.length === 0 && <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No budgets for this month yet. Choose a category and set a limit below.</p>}
          {progress.map((p) => {
            const over = p.spent > p.limit, near = !over && p.percent >= 80;
            return (
              <article key={p.category} className={`rounded-xl border p-4 ${tone(over, near, "border-rose-200 bg-rose-50", "border-amber-200 bg-amber-50", "border-slate-200 bg-slate-50")}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h4 className="text-sm font-bold text-slate-800">{p.category}</h4>
                  <p className={`text-xs font-semibold ${tone(over, near, "text-rose-700", "text-amber-700", "text-slate-500")}`}>{cur(p.spent)} of {cur(p.limit)}</p>
                </div>
                <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-white/80" role="progressbar" aria-label={`${p.category} budget used`}
                  aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(100, Math.round(p.percent))}>
                  <div className={`h-full rounded-full transition-all ${tone(over, near, "bg-rose-500", "bg-amber-500", "bg-blue-700")}`} style={{ width: `${Math.min(100, p.percent)}%` }} />
                </div>
                <p className={`mt-2 text-xs ${tone(over, near, "font-bold text-rose-700", "font-semibold text-amber-700", "text-slate-500")}`}>
                  {over ? `Over budget by ${cur(p.spent - p.limit)}` : `${cur(Math.max(0, p.limit - p.spent))} remaining · ${Math.round(p.percent)}% used`}
                </p>
                <button type="button" className="sb-link mt-2"
                  onClick={() => { const next = { ...limits }; delete next[`${month}|${p.category}`]; saveLimits(next); }}>Remove limit</button>
              </article>
            );
          })}
        </div>
      </div>

      <div id="budget-details" className="sb-panel">
        <h3 className="dash-card-title">Category limits</h3>
        <form id="budget-form" className="budget-form" onSubmit={save}>
          <div className="sb-field">
            <label htmlFor="budget-category">Category</label>
            <select id="budget-category" required value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="" disabled>Select a category</option>
              {cats.active.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="sb-field">
            <label htmlFor="budget-amount">Monthly limit (₦)</label>
            <input id="budget-amount" type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="e.g. 50000" required value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <button type="submit" className="sb-btn sb-btn-primary">Save limit</button>
        </form>
        {error && <p className="sb-error" role="alert">{error}</p>}
      </div>
    </section>
  );
}
