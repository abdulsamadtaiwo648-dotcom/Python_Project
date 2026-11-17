/** Naira amount that drops the kobo when there are none: 52600 -> ₦52,600. */
export function money(value: number | null | undefined): string {
  const amount = Number.isFinite(value as number) ? (value as number) : 0;
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  const whole = Math.abs(abs - Math.round(abs)) < 0.005;
  return `₦${sign}${abs.toLocaleString("en-NG", whole ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Parse a saved "YYYY-MM-DD hh:mm AM" (or ISO) date into a Date, or null. The server stores UTC. */
export function parseSaved(value: string | null | undefined): Date | null {
  if (!value) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})\s*(AM|PM)?)?/i.exec(value);
  if (!m) return null;
  let hour = m[4] ? Number(m[4]) : 0;
  if (m[6]) hour = (hour % 12) + (m[6].toUpperCase() === "PM" ? 12 : 0);
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), hour, m[5] ? Number(m[5]) : 0));
}

export function relativeDay(value: string): string {
  const d = parseSaved(value);
  if (!d) return value;
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((start(new Date()) - start(d)) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days > 1 && days < 7) return d.toLocaleDateString("en-GB", { weekday: "long" });
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
