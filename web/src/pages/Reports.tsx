import { useEffect, useState } from "react";
import type { Range } from "../analytics";
import Analysis from "../components/Analysis";
import MonthPicker from "../components/MonthPicker";
import YearPicker from "../components/YearPicker";
import { useDashboardMonth } from "../dashboardMonth";
import { useData } from "../data";
import { LockedPage } from "../components/Upgrade";
import { monthNow } from "../month";

/** Reports: the business analysis for a month or a year, with the same month picker as the dashboard. */
export default function Reports() {
  const { can } = useData();
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

      <Analysis page="reports" range={range} />
    </>
  );
}
