/** Horizontal filter chips. aria-pressed marks the active one. */
export function FilterChips<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="ui-chips" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" className="ui-chip" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}
