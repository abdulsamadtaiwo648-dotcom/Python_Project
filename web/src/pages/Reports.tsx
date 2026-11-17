import { useEffect } from "react";
import { Link } from "react-router-dom";
import Analysis from "../components/Analysis";
import { useData } from "../data";
import { money } from "../format";
import { KpiRow } from "./Dashboard";

export default function Reports() {
  const { summary: s } = useData();
  useEffect(() => { document.title = "Reports | SoloBiz"; }, []);
  const stock = s?.low_stock_items ?? [];
  return (
    <>
      <section id="tab-reports-content" className="tab-content" aria-labelledby="reports-title">
        <div className="dash-head reports-head"><h2 className="dash-title" id="reports-title">Reports</h2></div>
      </section>
      <div id="cfo-dashboard"><KpiRow /></div>
      <section id="tab-dashboard-content" className="tab-content space-y-6">
        <div className="flex items-center justify-between gap-5 overflow-hidden rounded-2xl border border-slate-200 bg-white px-5 py-5 shadow-sm sm:px-7 sm:py-6">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-600" aria-hidden="true" />Your business
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-[1.75rem]">Welcome back, {s?.username ?? ""}</h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">A clear view of this month’s sales, expenses and cash flow.</p>
          </div>
        </div>
      </section>
      <Analysis page="reports" />
      <section id="daily-business-checkin" className="dash-panel mb-6 w-full max-w-[1080px] rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="daily-checkin-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="daily-checkin-heading" className="text-base font-bold text-slate-900">Today at a glance</h2>
            <p className="mt-1 text-xs text-slate-500">A quick check of today’s money in and out.</p>
          </div>
          <span className="text-xs font-medium text-slate-500">{s?.today}</span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-medium text-slate-500">Collected today</p>
            <p className="mt-2 text-xl font-semibold tracking-tight text-emerald-700">{money(s?.today_collected)}</p>
          </article>
          <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-medium text-slate-500">Expenses today</p>
            <p className="mt-2 text-xl font-semibold tracking-tight text-rose-700">{money(s?.today_expenses)}</p>
          </article>
          <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-medium text-slate-500">Net cash today</p>
            <p className={`mt-2 text-xl font-semibold tracking-tight ${(s?.today_net ?? 0) >= 0 ? "text-slate-900" : "text-amber-700"}`}>{money(s?.today_net)}</p>
            <p className="mt-1 text-[11px] text-slate-500">Collected minus expenses</p>
          </article>
        </div>
        <div className="mt-4 border-t border-slate-100 pt-4">
          <h3 className="text-sm font-semibold text-slate-800">Needs attention</h3>
          <div className="mt-2 space-y-2" aria-live="polite">
            {(s?.outstanding_sale_count ?? 0) > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-3 py-3">
                <p className="text-sm text-amber-900"><strong>{s?.outstanding_sale_count}</strong> sale{s?.outstanding_sale_count === 1 ? "" : "s"} with a balance to follow up.</p>
                <Link to="/sales" className="text-sm font-semibold text-amber-900 underline underline-offset-2">Review sales</Link>
              </div>
            )}
            {stock.length > 0 && (
              <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl bg-rose-50 px-3 py-3">
                <div className="text-sm text-rose-900">
                  <strong>{stock.length}</strong> tracked item{stock.length === 1 ? "" : "s"} at or below their alert level.
                  <p className="mt-1 text-xs text-rose-800">{stock.slice(0, 5).map((i) => `${i.item_name} (${i.stock})`).join(", ")}{stock.length > 5 ? ` and ${stock.length - 5} more` : ""}</p>
                </div>
                <Link to="/inventory" className="text-sm font-semibold text-rose-900 underline underline-offset-2">Review stock</Link>
              </div>
            )}
            {!(s?.outstanding_sale_count) && stock.length === 0 && (
              <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-600">Nothing needs attention based on your current sales and stock.</p>
            )}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/sales" className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white no-underline hover:bg-blue-700">Record a sale</Link>
          <Link to="/expenses" className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 no-underline hover:bg-slate-50">Record an expense</Link>
        </div>
      </section>
    </>
  );
}
