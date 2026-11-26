import type { Slice } from "../analytics";

const COLOURS = ["#1d4ed8", "#60a5fa", "#0f766e", "#94a3b8", "#f59e0b", "#7c3aed", "#e11d48", "#334155"];

/** A ring showing how a total splits into parts. The parts are drawn in order, from the top. */
export default function Donut({ slices, centre, label }: { slices: Slice[]; centre: string; label: string }) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = 40, circumference = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg viewBox="0 0 100 100" className="h-36 w-36 flex-shrink-0" role="img" aria-label={label}>
      <circle cx="50" cy="50" r={r} fill="none" stroke="#f1f5f9" strokeWidth="14" />
      {total > 0 && slices.map((s, i) => {
        const length = (s.value / total) * circumference;
        const el = (
          <circle key={s.label} cx="50" cy="50" r={r} fill="none" stroke={COLOURS[i % COLOURS.length]} strokeWidth="14"
            strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} transform="rotate(-90 50 50)" />
        );
        offset += length;
        return el;
      })}
      <text x="50" y="50" textAnchor="middle" dominantBaseline="middle" className="fill-slate-900 text-[9px] font-bold">{centre}</text>
    </svg>
  );
}

export { COLOURS };
