import { useEffect } from "react";
import { Link } from "react-router-dom";
import Analysis, { whenLabel } from "../components/Analysis";
import { useData } from "../data";
import { money, parseSaved } from "../format";

export function KpiRow() {
  const { summary } = useData();
  const s = summary;
  const low = s?.low_stock_items.length ?? 0;
  return (
    <div id="kpi-row" className="grid grid-cols-2 lg:grid-cols-4">
      <div className="kpi-card">
        <p className="kpi-label">Income this month</p>
        <span className="stat-value" id="top-sales">{money(s?.month_income)}</span>
        <p className="kpi-note">{s?.income_note ?? ""}</p>
      </div>
      <div className="kpi-card">
        <p className="kpi-label">Expenses this month</p>
        <span className="stat-value" id="top-expenses">{money(s?.month_expenses)}</span>
        <p className="kpi-note">{s?.expense_note ?? ""}</p>
      </div>
      <div id="kpi-net-cash-flow" className="kpi-card">
        <p className="kpi-label">Net profit</p>
        <span className={`stat-value ${(s?.month_net ?? 0) < 0 ? "text-amber-600" : ""}`} id="top-profit">{money(s?.month_net)}</span>
        <p className="kpi-note">{s?.net_note ?? ""}</p>
      </div>
      <div className="kpi-card">
        <p className="kpi-label">Low stock</p>
        <span className="stat-value" id="kpi-low-stock">{low} item{low === 1 ? "" : "s"}</span>
        <p className="kpi-note">{low ? "Restock soon" : "Everything is stocked"}</p>
      </div>
    </div>
  );
}

export function RecentSales() {
  const { sales } = useData();
  const recent = [...sales]
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
          {recent.length === 0 && <li className="py-6 text-center text-sm text-slate-500">No sales yet. Record your first sale to see it here.</li>}
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
  useEffect(() => { document.title = "Dashboard | SoloBiz"; }, []);
  return (
    <>
      <div id="cfo-dashboard" className="transition-all duration-300">
        <div className="page-head mb-4">
          <div className="min-w-0">
            <h2 className="page-title">Dashboard</h2>
            <p className="page-sub">Here is how your business is doing today.</p>
          </div>
          <Link to="/sales" className="sb-btn sb-btn-primary">
            <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path d="M12 5v14M5 12h14" /></svg>
            New sale
          </Link>
        </div>
        <KpiRow />
      </div>
      <Analysis page="dashboard" />
      <RecentSales />
    </>
  );
}
