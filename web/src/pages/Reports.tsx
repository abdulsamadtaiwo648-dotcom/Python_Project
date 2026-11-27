import { useEffect, useMemo, useState } from "react";
import type { Range } from "../analytics";
import type { Expense, MoneyInItem, Sale } from "../types";
import Analysis from "../components/Analysis";
import InfoTip from "../components/InfoTip";
import MonthPicker from "../components/MonthPicker";
import YearPicker from "../components/YearPicker";
import { useDashboardMonth } from "../dashboardMonth";
import { useData } from "../data";
import { compactNaira } from "../format";
import { dayOf, expenseSlices, inRange, rangeLabel, totalsInRange, type Slice } from "../analytics";
import { ListRow } from "../ui";
import Donut, { COLOURS } from "../components/Donut";
import { LockedPage } from "../components/Upgrade";
import { money } from "../format";
import { monthNow, ymLabel } from "../month";

/** Reports: the business analysis for a month or a year, with the same month picker as the dashboard. */
export default function Reports() {
  const { can, expenses, accounts, sales, moneyIn } = useData();
  const dm = useDashboardMonth();
  const [kind, setKind] = useState<"month" | "year">("month");
  const [pickedYear, setPickedYear] = useState<string | null>(null);
  useEffect(() => { document.title = "Reports | SoloBiz"; }, []);

  const currentYm = dm.current ?? monthNow();
  const currentYear = currentYm.slice(0, 4);
  const ym = dm.selected ?? currentYm;
  const year = pickedYear ?? currentYear;
  const range: Range = kind === "month" ? { kind: "month", ym } : { kind: "year", year };
  const years = Array.from(new Set(dm.months.map((m) => m.slice(0, 4))));
  const accountName = (id: number | null | undefined) => accounts.find((a) => a.id === id)?.name ?? "";

  if (!can("reports")) {
    return <LockedPage title="Reports" plan="Basic" text="See trends, sales by period and today at a glance. Reports come with the Basic and Pro plans." />;
  }
  return (
    <>
      <section id="tab-reports-content" className="tab-content" aria-labelledby="reports-title">
        <div className="dash-head reports-head"><h2 className="dash-title" id="reports-title">Reports</h2></div>
      </section>

      <section className="mb-4 flex flex-wrap items-center gap-3" aria-label="Choose the period to report on">
        <div role="group" aria-label="Report range" className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
          {(["month", "year"] as const).map((k) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${kind === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
              {k === "month" ? "Month" : "Year"}
            </button>
          ))}
        </div>
        {kind === "month"
          ? <MonthPicker value={ym} current={currentYm} months={dm.months} onChange={dm.setMonth} />
          : <YearPicker value={year} current={currentYear} years={years} onChange={setPickedYear} />}
      </section>

      {kind === "month" && dm.summary?.cash && (
        <section className="sb-panel mb-4" aria-labelledby="reports-cash-title">
          <h3 id="reports-cash-title" className="text-sm font-semibold text-slate-900">Cash in {ymLabel(ym)}</h3>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <div>
              <dt className="flex items-center text-xs text-slate-500">Sales payments received
                <InfoTip label="Sales payments received">Payments customers made this month, counted on the day each was paid.</InfoTip>
              </dt>
              <dd className="mt-1 text-base font-semibold tabular-nums text-slate-900">{money(dm.summary.cash.payments_received)}</dd>
            </div>
            <div>
              <dt className="flex items-center text-xs text-slate-500">Money in
                <InfoTip label="Money in">Owner contributions, loans, refunds and other income this month. Transfers between your accounts are not included.</InfoTip>
              </dt>
              <dd className="mt-1 text-base font-semibold tabular-nums text-emerald-700">{money(dm.summary.cash.money_in)}</dd>
            </div>
            <div>
              <dt className="flex items-center text-xs text-slate-500">Expenses paid
                <InfoTip label="Expenses paid">Everything spent this month, from any account.</InfoTip>
              </dt>
              <dd className="mt-1 text-base font-semibold tabular-nums text-rose-700">{money(dm.summary.cash.expenses)}</dd>
            </div>
            <div>
              <dt className="flex items-center text-xs text-slate-500">Net cash movement
                <InfoTip label="Net cash movement">Sales payments received, plus money in, minus expenses paid. Profit is different: it is sales minus expenses.</InfoTip>
              </dt>
              <dd className={`mt-1 text-base font-bold tabular-nums ${(dm.summary.cash.net_cash_movement ?? 0) < 0 ? "text-rose-700" : "text-slate-900"}`}>{money(dm.summary.cash.net_cash_movement ?? dm.summary.cash.cash_balance)}</dd>
            </div>
          </dl>
        </section>
      )}

      <Analysis page="reports" range={range} />

      <ReportsExtras sales={sales} expenses={expenses} moneyIn={moneyIn} range={range} />

      <section className="sb-panel mt-4 grid gap-6 md:grid-cols-2" aria-labelledby="reports-spend-title">
        <h3 id="reports-spend-title" className="text-sm font-semibold text-slate-900 md:col-span-2">Where the money went · {rangeLabel(range)}</h3>
        <Breakdown title="By category" slices={expenseSlices(expenses, range, "category", accountName)} label="Expenses by category" />
        <Breakdown title="By account" slices={expenseSlices(expenses, range, "account", accountName)} label="Expenses by account" />
      </section>
    </>
  );
}

/** A donut with its legend: each part's amount and share of the total. */
function Breakdown({ title, slices, label }: { title: string; slices: Slice[]; label: string }) {
  const total = slices.reduce((t, x) => t + x.value, 0);
  const coloured = slices.map((x, i) => ({ ...x, colour: COLOURS[i % COLOURS.length] }));
  return (
    <div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {total <= 0 ? (
        <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">No expenses in this period.</p>
      ) : (
        <div className="flex items-center gap-4">
          <Donut slices={slices} centre={short(total)} label={`${label}: total ${money(total)}`} />
          <ul className="min-w-0 flex-1 space-y-2">
            {coloured.map((x) => (
              <li key={x.label} className="flex items-center justify-between gap-2 text-sm">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2.5 w-2.5 flex-shrink-0 rounded-sm" style={{ background: x.colour }} aria-hidden="true" />
                  <span className="truncate text-slate-800">{x.label}</span>
                </span>
                <span className="flex-shrink-0 tabular-nums text-slate-900">{money(x.value)} <span className="text-xs text-slate-500">{Math.round((x.value / total) * 100)}%</span></span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** ₦36.6M style, so the total fits in the middle of the ring. */
const short = compactNaira;

/** Profit and loss for the period, top products, and a CSV export of everything in the period. */
function ReportsExtras(props: { sales: Sale[]; expenses: Expense[]; moneyIn: MoneyInItem[]; range: Range }) {
  const { sales, expenses, moneyIn, range } = props;
  const totals = totalsInRange(sales, expenses, range, moneyIn);
  const profit = totals.value - totals.expenses;
  const topProducts = useMemo(() => {
    const byName = new Map<string, { name: string; amount: number; count: number }>();
    for (const sale of sales) {
      if (!inRange(dayOf(sale), range)) continue;
      const name = sale.description?.trim() || "Sale";
      const entry = byName.get(name) ?? { name, amount: 0, count: 0 };
      entry.amount += sale.total_value;
      entry.count += 1;
      byName.set(name, entry);
    }
    return [...byName.values()].sort((a, b) => b.amount - a.amount).slice(0, 5);
  }, [sales, range]);

  function exportCsv() {
    const rows: string[][] = [["Date", "Type", "Description", "Category or customer", "Amount"]];
    for (const s of sales) if (inRange(dayOf(s), range)) rows.push([dayOf(s), "Sale", s.description ?? "", s.customer_name ?? "", String(s.total_value)]);
    for (const e of expenses) if (inRange(dayOf(e), range)) rows.push([dayOf(e), "Expense", e.description ?? "", e.category ?? "", String(-e.amount)]);
    for (const m of moneyIn) if (inRange(dayOf(m), range)) rows.push([dayOf(m), "Money in", m.description ?? "", m.kind ?? "", String(m.amount)]);
    const csv = rows.map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `solobiz-${rangeLabel(range).replace(/\s+/g, "-").toLowerCase()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="mt-4 grid gap-4 md:grid-cols-2" aria-label="Profit and top products">
      <div className="sb-panel">
        <h3 className="text-sm font-semibold text-slate-900">Profit and loss · {rangeLabel(range)}</h3>
        <dl className="mt-3 divide-y divide-slate-100">
          <div className="flex items-center justify-between py-2"><dt className="text-sm text-slate-600">Sales</dt><dd className="text-sm font-semibold tabular-nums">{money(totals.value)}</dd></div>
          <div className="flex items-center justify-between py-2"><dt className="text-sm text-slate-600">Expenses</dt><dd className="text-sm font-semibold tabular-nums">−{money(totals.expenses)}</dd></div>
          <div className="flex items-center justify-between py-2">
            <dt className="text-sm font-semibold text-slate-900">Profit</dt>
            <dd className={`text-base font-bold tabular-nums ${profit < 0 ? "text-amber-700" : "text-slate-900"}`}>{money(profit)}</dd>
          </div>
        </dl>
        <p className="mt-2 text-xs text-slate-500">Sales minus expenses. Money in is cash, not a sale, so it is not in profit.</p>
        <button type="button" className="sb-btn sb-btn-secondary mt-3" onClick={exportCsv}>Export CSV</button>
      </div>
      <div className="sb-panel">
        <h3 className="text-sm font-semibold text-slate-900">Top products · {rangeLabel(range)}</h3>
        {topProducts.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No sales in this period.</p>
        ) : (
          <div className="mt-2">
            {topProducts.map((p) => (
              <ListRow key={p.name} title={p.name} subtitle={`${p.count} ${p.count === 1 ? "sale" : "sales"}`} amount={money(p.amount)} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
