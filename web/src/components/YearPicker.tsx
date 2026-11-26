/** ◀ Year ▶ with a list of years, never past the current year. */
export default function YearPicker(props: { value: string; current: string; years: string[]; onChange: (year: string) => void }) {
  const { value, current, years, onChange } = props;
  const options = Array.from(new Set([current, value, ...years])).filter((y) => y <= current).sort().reverse();
  const btn = "sb-btn sb-btn-small sb-btn-secondary";
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Choose year">
      <button type="button" className={btn} aria-label="Previous year" onClick={() => onChange(String(Number(value) - 1))}>◀</button>
      <label className="sr-only" htmlFor="year-select">Year</label>
      <select id="year-select" value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-900">
        {options.map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
      <button type="button" className={btn} aria-label="Next year" disabled={value >= current}
        onClick={() => onChange(String(Number(value) + 1))}>▶</button>
      {value !== current && <button type="button" className={btn} onClick={() => onChange(current)}>This year</button>}
    </div>
  );
}
