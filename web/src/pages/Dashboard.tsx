import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { lastMonths } from "../analytics";
import InfoTip from "../components/InfoTip";
import { ActionSheet, FAB, StatCard } from "../ui";
import MonthPicker from "../components/MonthPicker";
import { useDashboardMonth } from "../dashboardMonth";
import { useData } from "../data";
import { money, relativeDay } from "../format";
import { dayOf } from "../analytics";
import { monthNow, ymLabel } from "../month";
import { useCashAtHand } from "../cashAtHand";
import { budgetAlerts } from "../budgetAlerts";
import { useSession } from "../session";
import type { DashboardSummary, Expense, MoneyInItem, Sale } from "../types";

/** Home: this month in four numbers, six months at a glance, and the latest activity. */
export default function Dashboard() {
  const { summary: fromContext, sales, expenses, moneyIn, accounts, online } = useData();
  const navigate = useNavigate();
  const [quickAdd, setQuickAdd] = useState(false);
  const lowStock = fromContext?.low_stock_items.length ?? 0;
  const dm = useDashboardMonth();
  const s: DashboardSummary | null = dm.summary ?? fromContext;
  const ym = dm.selected ?? monthNow();
  const { user } = useSession();
  // Budgets are saved in this browser (see Budget). Read them here to warn when a category is near its limit.
  const storedLimits = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem(`solobiz:budgets:${user?.id ?? "anon"}`) || "{}") as Record<string, number>;
    } catch {
      return {};
    }
  }, [user?.id]);
  const budgetWarnings = budgetAlerts(storedLimits, expenses, ym);
  const monthName = ymLabel(ym);
  const cashAtHand = useCashAtHand(accounts, s);
  const name = s?.username ?? "";

  useEffect(() => { document.title = "Home | SoloBiz"; }, []);

  const profit = s?.month_net ?? 0;
  // The six months end at the latest month that has any record, so the chart has no empty months at the end.
  const buckets = lastMonths(sales, expenses, latestMonthWithData(sales, expenses, moneyIn) ?? ym, 6, moneyIn);
  const peak = Math.max(1, ...buckets.flatMap((b) => [b.sales + b.moneyIn, b.expenses]));
  // Recent activity follows the month picker.
  const inMonth = (r: { entry_date?: string; date: string }) => dayOf(r).startsWith(ym);
  const recent = recentActivity(sales.filter(inMonth), expenses.filter(inMonth), 5);

  return (
    <div className="space-y-5" id="home">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold text-slate-900">{greeting()}{name ? `, ${name}` : ""}</p>
        </div>
        <MonthPicker value={ym} current={dm.current ?? monthNow()} months={dm.months} onChange={dm.setMonth} />
      </header>

      {dm.notice && (
        <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span>{dm.notice.message}</span>
          <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={() => dm.setMonth(dm.notice!.current_month)}>
            Show {ymLabel(dm.notice.current_month)}
          </button>
        </div>
      )}

      {lowStock > 0 && (
        <Link to="/inventory" className="flex items-center justify-between rounded-xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
          <span>{lowStock} {lowStock === 1 ? "product is" : "products are"} running low</span>
          <span className="text-blue-700">Restock →</span>
        </Link>
      )}

      {budgetWarnings.map((b) => (
        <Link key={`budget-${b.category}`} to="/budget" className="flex items-center justify-between rounded-xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
          <span>{b.category} is at {Math.round(b.percent)}% of its budget</span>
          <span className="text-blue-700">See budget →</span>
        </Link>
      ))}
      {typeof cashAtHand === "number" && cashAtHand < 0 && (
        <Link to="/money?tab=accounts" className="flex items-center justify-between rounded-xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
          <span>Overspent: cash at hand is {money(cashAtHand)}</span>
          <span className="text-blue-700">See accounts →</span>
        </Link>
      )}
      {s && s.total_outstanding > 0 && (
        <Link to="/sales" className="flex items-center justify-between rounded-xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
          <span>{money(s.total_outstanding)} still owed by customers</span>
          <span className="text-blue-700">See sales →</span>
        </Link>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="This month at a glance">
        <Card label="Sales" tip={`Money collected from sales in ${monthName}.`} value={s ? money(s.month_income) : null} />
        <Card label="Expenses" tip={`Expenses paid in ${monthName}.`} value={s ? money(s.month_expenses) : null} />
        <Card label="Profit" tip={`Sales minus expenses in ${monthName}.`}
          value={s ? money(profit) : null} tone={profit < 0 ? "warning" : undefined} />
        <Card label="Cash at hand" tip="All your account balances today, added together."
          value={cashAtHand === undefined ? null : cashAtHand === null ? "—" : money(cashAtHand)}
          tone={(cashAtHand ?? 0) < 0 ? "warning" : undefined}
          link={{ to: "/money?tab=accounts", label: "See accounts →" }} />
      </section>

      <section className="sb-panel" aria-labelledby="home-chart-title">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 id="home-chart-title" className="text-sm font-semibold text-slate-900">Last 6 months</h3>
          <div className="flex items-center gap-3 text-[11px] font-medium text-slate-500">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" />Money in</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-slate-300" />Money out</span>
          </div>
        </div>
        {!s ? (
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" aria-hidden="true" />
        ) : (
          <div className="flex h-40 items-end gap-2" role="img"
            aria-label={buckets.map((b) => `${b.label}: in ${money(b.sales + b.moneyIn)}, out ${money(b.expenses)}`).join(". ")}>
            {buckets.map((b) => (
              <div key={b.label + b.sortDate} className="flex flex-1 flex-col items-center gap-1">
                <div className="flex h-32 w-full items-end justify-center gap-1">
                  <div className="w-3 rounded-t bg-emerald-500" style={{ height: barHeight(b.sales + b.moneyIn, peak) }} />
                  <div className="w-3 rounded-t bg-slate-300" style={{ height: barHeight(b.expenses, peak) }} />
                </div>
                <span className="text-[10px] text-slate-500">{b.label}</span>
              </div>
            ))}
          </div>
        )}
        {!online && <p className="mt-2 text-xs text-slate-500">Showing what is saved on this device.</p>}
      </section>

      <section className="sb-panel" aria-labelledby="home-recent-title">
        <div className="mb-2 flex items-center justify-between">
          <h3 id="home-recent-title" className="text-sm font-semibold text-slate-900">Recent activity</h3>
          <Link to="/sales" className="text-xs font-semibold text-blue-700 hover:text-blue-900">All sales</Link>
        </div>
        {!s ? (
          <div className="space-y-2" aria-hidden="true">
            {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-slate-100" />)}
          </div>
        ) : recent.length === 0 ? (
          <div className="py-6 text-center">
            <p className="text-sm text-slate-500">Nothing recorded yet.</p>
            <Link to="/sales" className="sb-btn sb-btn-primary mt-3 inline-flex">Record a sale</Link>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {recent.map((r) => (
              <li key={r.key} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">{r.title}</p>
                  <p className="truncate text-xs text-slate-500">{r.sub}</p>
                </div>
                <p className={`flex-shrink-0 text-sm font-semibold tabular-nums ${r.kind === "sale" ? "text-emerald-700" : "text-slate-800"}`}>
                  {r.kind === "sale" ? "+" : "−"}{money(r.amount)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <FAB label="Add something" onClick={() => setQuickAdd(true)} />
      {quickAdd && (
        <ActionSheet title="Add something" onClose={() => setQuickAdd(false)} options={[
          { label: "Sale", sub: "Record something you sold", onSelect: () => navigate("/sales?new=1") },
          { label: "Expense", sub: "Record money you spent", onSelect: () => navigate("/expenses?new=1") },
          { label: "Money in", sub: "Owner contribution, loan or other income", onSelect: () => navigate("/money?tab=moneyin&new=1") },
        ]} />
      )}
    </div>
  );
}

function Card(props: { label: string; tip: string; value: string | null; tone?: "money-in" | "warning" | "danger"; link?: { to: string; label: string } }) {
  return (
    <StatCard label={props.label} value={props.value} tone={props.tone}
      info={<InfoTip label={props.label}>{props.tip}</InfoTip>}
      footer={props.link && <Link to={props.link.to}>{props.link.label}</Link>} />
  );
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function barHeight(value: number, peak: number): string {
  if (value <= 0) return "0px";
  return `${Math.max(3, Math.round((value / peak) * 128))}px`;
}

interface Activity { key: string; kind: "sale" | "expense"; title: string; sub: string; amount: number; day: string }

/** The latest month (YYYY-MM) that has a sale, expense or money in, or null when there are none. */
function latestMonthWithData(sales: Sale[], expenses: Expense[], moneyIn: MoneyInItem[]): string | null {
  let latest = "";
  for (const r of [...sales, ...expenses, ...moneyIn]) {
    const month = dayOf(r).slice(0, 7);
    if (month > latest) latest = month;
  }
  return latest || null;
}

/** The latest sales and expenses together, newest first, by business day. */
function recentActivity(sales: Sale[], expenses: Expense[], count: number): Activity[] {
  const items: Activity[] = [
    // Description is the title; the small line is category (or customer for sales) and the day.
    ...sales.map((s) => ({
      key: `s${s.id}`, kind: "sale" as const, title: s.description || "Sale",
      sub: `${s.customer_name || "Walk-in customer"} · ${relativeDay(s.entry_date || s.date)}`, amount: s.amount_paid, day: dayOf(s),
    })),
    ...expenses.map((e) => ({
      key: `e${e.server_id}`, kind: "expense" as const, title: e.description || "Expense",
      sub: `${e.category || "Other"} · ${relativeDay(e.entry_date || e.date)}`, amount: e.amount, day: dayOf(e),
    })),
  ];
  return items.sort((a, b) => b.day.localeCompare(a.day) || b.key.localeCompare(a.key)).slice(0, count);
}

