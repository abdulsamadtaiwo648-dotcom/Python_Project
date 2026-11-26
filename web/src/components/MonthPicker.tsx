import { shiftYm, ymLabel } from "../month";

/** ◀ Month ▶ with a list of months, never past the current month. */
export default function MonthPicker(props: { value: string; current: string; months: string[]; onChange: (ym: string) => void }) {
  const { value, current, months, onChange } = props;
  const options = Array.from(new Set([current, value, ...months])).filter((m) => m <= current).sort().reverse();
  const btn = "sb-btn sb-btn-small sb-btn-secondary";
  return (
    <div className="flex w-full max-w-md flex-col items-stretch gap-1 sm:w-auto">
      <div className="flex items-center gap-1.5" role="group" aria-label="Choose month">
        <button type="button" className={btn} aria-label="Previous month" onClick={() => onChange(shiftYm(value, -1))}>◀</button>
        <label className="sr-only" htmlFor="month-select">Month</label>
        <select id="month-select" value={value} onChange={(e) => onChange(e.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-900">
          {options.map((m) => (
            <option key={m} value={m}>{ymLabel(m)}{months.includes(m) || m === current ? "" : " (no records)"}</option>
          ))}
        </select>
        <button type="button" className={btn} aria-label="Next month" disabled={value >= current}
          onClick={() => onChange(shiftYm(value, 1))}>▶</button>
      </div>
      {value !== current && (
        <button type="button" className="self-end text-xs font-semibold text-blue-700 hover:text-blue-900" onClick={() => onChange(current)}>Back to this month</button>
      )}
    </div>
  );
}
