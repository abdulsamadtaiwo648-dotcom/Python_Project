import { useEffect } from "react";
import { Link } from "react-router-dom";
import Analysis, { whenLabel } from "../components/Analysis";
import MonthPicker from "../components/MonthPicker";
import { useDashboardMonth } from "../dashboardMonth";
import { useData } from "../data";
import { money, parseSaved } from "../format";
import { monthNow, monthOfRecord, ymLabel } from "../month";
import type { CashSummary, DashboardSummary } from "../types";

/** Cash for the month shown: what came in, what went out, and the balance. */
export function CashCard({ cash, phrase }: { cash: CashSummary; phrase: string }) {
  const rows: [string, number, string][] = [
    ["Sales collected", cash.sales_collected, "text-slate-900"],
    ["Money in", cash.money_in, "text-slate-900"],
    ["Expenses", cash.expenses, "text-rose-700"],
    ["Profit (sales − expenses)", cash.profit, cash.profit < 0 ? "text-rose-700" : "text-slate-900"],
    ["Cash balance (sales + money in − expenses)", cash.cash_balance, cash.cash_balance < 0 ? "text-rose-700" : "text-slate-900"],
  ];
  return (
    <section id="dashboard-cash" className="dash-panel mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="dashboard-cash-heading">
      <h3 id="dashboard-cash-heading" className="text-base font-bold text-slate-900">Cash {phrase}</h3>
      <p className="mt-1 text-xs text-slate-500">Money in is cash but not a sale, so it changes the balance and not the profit.</p>
      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {rows.map(([label, value, color]) => (
          <div key={label} className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-2">
            <dt className="text-sm text-slate-600">{label}</dt>
            <dd className={`text-sm font-semibold ${color}`}>{money(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function KpiRow({ summary: given }: { summary?: DashboardSummary | null } = {}) {
  const { summary: fromContext } = useData();
  const s = given ?? fromContext;
  const low = s?.low_stock_items.length ?? 0;
  // "this month", or the name of the month being shown
  const phrase = !s || s.selected_month === s.current_month ? "this month" : `in ${ymLabel(s.selected_month)}`;
  return (
    <div id="kpi-row" className="grid grid-cols-2 lg:grid-cols-4">
      <div className="kpi-card">
        <p className="kpi-label">Income {phrase}</p>
        <span className="stat-value" id="top-sales">{money(s?.month_income)}</span>
        <p className="kpi-note">{s?.income_note ?? ""}</p>
      </div>
      <div className="kpi-card">
        <p className="kpi-label">Expenses {phrase}</p>
        <span className="stat-value" id="top-expenses">{money(s?.month_expenses)}</span>
        <p className="kpi-note">{s?.expense_note ?? ""}</p>
      </div>
      <div id="kpi-net-cash-flow" className="kpi-card">
        <p className="kpi-label">{(s?.month_net ?? 0) < 0 ? `Net loss ${phrase}` : `Net profit ${phrase}`}</p>
        <span className={`stat-value ${(s?.month_net ?? 0) < 0 ? "text-rose-700" : ""}`} id="top-profit">{money(s?.month_net)}</span>
        <p className="kpi-note">
          {(s?.month_net ?? 0) < 0 && (s?.month_income ?? 0) === 0
            ? `No income recorded ${phrase}; expenses are ${money(s?.month_expenses)}.`
            : (s?.month_net ?? 0) < 0
              ? `Spending is ${money(Math.abs(s?.month_net ?? 0))} more than income ${phrase}.`
              : (s?.net_note ?? "")}
        </p>
      </div>
      <div className="kpi-card">
        <p className="kpi-label">Low stock</p>
        <span className="stat-value" id="kpi-low-stock">{low} item{low === 1 ? "" : "s"}</span>
        <p className="kpi-note">{low ? "Restock soon" : "Everything is stocked"}</p>
      </div>
    </div>
  );
}

export function RecentSales({ month, current }: { month?: string | null; current?: string | null }) {
  const { sales } = useData();
  const inMonth = month ? sales.filter((s) => monthOfRecord(s) === month) : sales;
  const recent = [...inMonth]
    .sort((a, b) => (parseSaved(b.date)?.getTime() ?? 0) - (parseSaved(a.date)?.getTime() ?? 0))
    .slice(0, 5);
  return (
    <div id="dashboard-bottom-grid" className="mb-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section id="dashboard-recent-sales" className="dash-panel min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="dashboard-recent-heading">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 id="dashboard-recent-heading" className="text-base font-bold text-slate-900">Recent sales</h3>
          <Link to="/sales" className="text-sm font-semibold text-blue-700 hover:text-blue-900">View all</Link>
        </div>
        <ul id="dashboard-recent-list" className="divide-y divide-slate-100" aria-live="polite">
          {recent.length === 0 && (
            <li className="py-6 text-center text-sm text-slate-500">
              {month && current && month !== current ? `No sales in ${ymLabel(month)}.` : "No sales yet. Record your first sale to see it here."}
            </li>
          )}
          {recent.map((s) => {
            const owing = s.total_value - s.amount_paid > 0.005;
            return (
              <li key={s.id} className="recent-row">
                <span className="recent-name">{s.customer_name || "Walk-in Customer"}</span>
                <span className={`recent-when${owing ? " is-owing" : ""}`}>{whenLabel(s.date)}{owing ? " · Balance due" : ""}</span>
                <span className="recent-amount">{money(s.total_value)}</span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}

export default function Dashboard() {
  const { summary: fromContext } = useData();
  const dm = useDashboardMonth();
  const summary = dm.summary ?? fromContext;
  useEffect(() => { document.title = "Dashboard | SoloBiz"; }, []);
  const todayLabel = new Date().toLocaleDateString("en-NG", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return (
    <>
      {/* Phones only: the welcome sits in the page, apart from the fixed header (desktop has it in the top bar). */}
      <section className="welcome-block lg:hidden" aria-label="Welcome">
        <div className="min-w-0">
          <h2 className="truncate">Welcome back, {summary?.username ?? ""}</h2>
          <p>{todayLabel}</p>
        </div>
      </section>
      <div id="cfo-dashboard" className="transition-all duration-300">
        <div className="page-head mb-4">
          <div className="min-w-0">
            <h2 className="page-title">Dashboard</h2>
            <p className="page-sub">Here is how your business is doing in {ymLabel(dm.selected ?? monthNow())}.</p>
          </div>
          <Link to="/sales" className="sb-btn sb-btn-primary">
            <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path d="M12 5v14M5 12h14" /></svg>
            New sale
          </Link>
        </div>
        {dm.selected && dm.current && (
          <div className="mb-4">
            <MonthPicker value={dm.selected} current={dm.current} months={dm.months} onChange={dm.setMonth} />
          </div>
        )}
        {dm.notice && (
          <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <span>{dm.notice.message}</span>
            <button type="button" className="sb-btn sb-btn-small sb-btn-secondary"
              onClick={() => dm.setMonth(dm.notice!.current_month)}>Show {ymLabel(dm.notice.current_month)}</button>
          </div>
        )}
        <KpiRow summary={summary} />
      </div>
      {summary?.cash && (
        <CashCard cash={summary.cash} phrase={summary.selected_month === summary.current_month ? "this month" : `in ${ymLabel(summary.selected_month)}`} />
      )}
      <Analysis page="dashboard" range={{ kind: "month", ym: dm.selected ?? monthNow() }} />
      <RecentSales month={dm.selected} current={dm.current} />
    </>
  );
}
