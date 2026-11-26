/** A small line showing how a balance moved over recent months. Shape only: no labels. */
export default function Sparkline({ values, label }: { values: number[]; label: string }) {
  if (values.length < 2) return <div className="h-8" aria-hidden="true" />;
  const lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 100},${24 - ((v - lo) / span) * 22 - 1}`).join(" ");
  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="h-8 w-full" role="img" aria-label={label}>
      <polyline points={points} fill="none" stroke="#1d4ed8" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
