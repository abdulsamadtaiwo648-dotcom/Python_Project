import { shiftYm, ymLabel } from "../month";

/** ◀ Month ▶ with a list of months, never past the current month. */
export default function MonthPicker(props: { value: string; current: string; months: string[]; onChange: (ym: string) => void }) {
  const { value, current, months, onChange } = props;
  const options = Array.from(new Set([current, value, ...months])).filter((m) => m <= current).sort().reverse();
  const btn = "sb-btn sb-btn-small sb-btn-secondary";
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Choose month">
      <button type="button" className={btn} aria-label="Previous month" onClick={() => onChange(shiftYm(value, -1))}>◀</button>
      <label className="sr-only" htmlFor="month-select">Month</label>
      <select id="month-select" value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-900">
        {options.map((m) => (
          <option key={m} value={m}>{ymLabel(m)}{months.includes(m) || m === current ? "" : " (no records)"}</option>
        ))}
      </select>
      <button type="button" className={btn} aria-label="Next month" disabled={value >= current}
        onClick={() => onChange(shiftYm(value, 1))}>▶</button>
      {value !== current && (
        <button type="button" className={btn} onClick={() => onChange(current)}>This month</button>
      )}
    </div>
  );
}
