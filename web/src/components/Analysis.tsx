import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { chartBuckets, groupSales, PERIOD_PHRASE, totalsFor, type Period } from "../analytics";
import { useData } from "../data";
import { money, parseSaved } from "../format";
import TrendChart from "./TrendChart";

const PERIODS: [Period, string][] = [["daily", "Day"], ["weekly", "Week"], ["monthly", "Month"], ["yearly", "Year"]];
const LABELS: Record<Period, string> = { daily: "Per Day", weekly: "Per Week", monthly: "Per Month", yearly: "Per Year" };

/** "Business analysis": period totals, the chart, low stock and sales by period. */
export default function Analysis({ page }: { page: "dashboard" | "reports" }) {
  const { sales, expenses, summary } = useData();
  const [period, setPeriod] = useState<Period>("daily");
  const [open, setOpen] = useState<string | null>(null);
  const totals = useMemo(() => totalsFor(sales, expenses, period), [sales, expenses, period]);
  const buckets = useMemo(() => chartBuckets(sales, expenses, period), [sales, expenses, period]);
  const groups = useMemo(() => groupSales(sales, period), [sales, period]);
  const low = summary?.low_stock_items ?? [];
  const summaryText = period === "daily" ? "Analysis totals for today." : `Analysis totals for ${PERIOD_PHRASE[period]} to date.`;

  const card = (label: string, value: string, color = "text-slate-900") => (
    <article className="rounded-2xl border border-slate-200 bg-white p-3 sm:p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-base font-bold ${color}`}>{value}</p>
    </article>
  );

  return (
    <section id="dashboard-insights" className="space-y-4" aria-labelledby="dashboard-insights-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="dashboard-insights-heading" className="text-base font-bold text-slate-900">Business analysis</h2>
          <p className="mt-1 text-xs text-slate-500">Review sales and expenses for the selected period.</p>
        </div>
        <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Choose reporting period">
          {PERIODS.map(([p, label]) => (
            <button key={p} type="button" data-period={p} onClick={() => setPeriod(p)}
              className={`analytics-tab-btn rounded-lg px-3 py-1.5 text-xs font-semibold ${period === p ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {card("Sales value", money(totals.value))}
        {card("Collected", money(totals.collected), "text-emerald-700")}
        {card("Expenses", money(totals.expenses), "text-rose-700")}
        {card("Balance due", money(totals.balance), "text-amber-700")}
        {card("Net cash flow", money(totals.net), totals.net < 0 ? "text-rose-700" : "text-emerald-700")}
      </div>
      <p className="-mt-2 text-[10px] text-slate-400">{summaryText}</p>
      {totals.balance > 0 && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-medium text-amber-800" aria-live="polite">
          Some sales still have an outstanding balance.
        </p>
      )}

      <div id="dashboard-chart-row" className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="dash-panel min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="analytics-trend-heading">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 id="analytics-trend-heading" className="text-base font-semibold text-slate-900">Income vs expenses</h3>
              <p className="mt-1 text-xs text-slate-500">{page === "dashboard" ? "Last 12 months" : LABELS[period]}</p>
            </div>
            <div className="flex items-center gap-3 text-[10px] font-medium text-slate-500" aria-label="Chart legend">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-blue-600" />Sales collected</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-slate-300" />Expenses</span>
            </div>
          </div>
          <TrendChart buckets={buckets} limit={page === "dashboard" ? 12 : 7} />
        </section>

        <section id="dashboard-low-stock" className="dash-panel min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="dashboard-low-heading">
          <h3 id="dashboard-low-heading" className="text-base font-bold text-slate-900">Low stock</h3>
          <p className="mt-1 text-xs text-slate-500">Restock before these run out.</p>
          <ul className="mt-4 space-y-3">
            {low.slice(0, 6).map((item) => (
              <li key={item.item_name} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-sm text-slate-800">{item.item_name}</span>
                <span className={`flex-shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${item.stock <= 0 ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"}`}>
                  {item.stock <= 0 ? "Out of stock" : `${item.stock} left`}
                </span>
              </li>
            ))}
            {low.length === 0 && <li className="rounded-xl bg-slate-50 px-3 py-4 text-center text-sm text-slate-500">Nothing is running low.</li>}
          </ul>
          {low.length > 6 && <Link to="/inventory" className="mt-4 inline-block text-sm font-semibold text-blue-700 hover:text-blue-900">View all {low.length} items</Link>}
        </section>
      </div>

      {page === "reports" && (
        <section className="dash-panel min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-labelledby="analytics-history-heading">
          <h3 id="analytics-history-heading" className="text-base font-bold text-slate-900">Sales by period</h3>
          <p className="mt-0.5 text-[11px] text-slate-500">Open a period to see its recorded sales.</p>
          <div className="mt-3 max-h-[340px] space-y-2 overflow-y-auto" aria-live="polite">
            {groups.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No sales data available.</p>}
            {groups.map((g) => (
              <div key={g.label} className="rounded-xl border border-slate-200">
                <button type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                  aria-expanded={open === g.label} onClick={() => setOpen(open === g.label ? null : g.label)}>
                  <span className="text-sm font-semibold text-slate-900">{g.label}</span>
                  <span className="text-sm font-semibold text-slate-700">{money(g.volume)}</span>
                </button>
                {open === g.label && (
                  <ul className="divide-y divide-slate-100 border-t border-slate-100 px-4">
                    {g.items.map((s) => (
                      <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-xs text-slate-600">
                        <span className="min-w-0 truncate">{s.description} · {s.customer_name}</span>
                        <span className="flex-shrink-0 font-semibold text-slate-800">{money(s.total_value)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}

export function whenLabel(value: string): string {
  const d = parseSaved(value);
  if (!d) return "";
  const k = (x: Date) => x.toDateString();
  const now = new Date(), yesterday = new Date();
  yesterday.setDate(now.getDate() - 1);
  if (k(d) === k(now)) return "Today " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (k(d) === k(yesterday)) return "Yesterday";
  return d.toLocaleDateString("en-NG", { day: "numeric", month: "short" });
}
