import { shiftIso } from "./date-picker";

/** Today / Yesterday chips plus a calendar for anything older. Values are YYYY-MM-DD. */
export default function DatePicker({ value, today, onChange, label }: { value: string; today: string; onChange: (iso: string) => void; label: string }) {
  const chips = [{ iso: today, text: "Today" }, { iso: shiftIso(today, -1), text: "Yesterday" }];
  return (
    <div>
      <div className="ui-chips" role="group" aria-label={label}>
        {chips.map((c) => (
          <button key={c.iso} type="button" className="ui-chip" aria-pressed={value === c.iso} onClick={() => onChange(c.iso)}>{c.text}</button>
        ))}
        <input type="date" aria-label={`${label}, pick a date`} className="ui-input" style={{ width: "auto", minHeight: 40 }} value={value} max={today}
          onChange={(e) => e.target.value && onChange(e.target.value)} />
      </div>
    </div>
  );
}
