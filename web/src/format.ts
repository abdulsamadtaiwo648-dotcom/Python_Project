/** Naira amount that drops the kobo when there are none: 52600 -> ₦52,600. */
export function money(value: number | null | undefined): string {
  const amount = Number.isFinite(value as number) ? (value as number) : 0;
  // The minus goes before the naira sign: -₦1,500, not ₦-1,500.
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  const whole = Math.abs(abs - Math.round(abs)) < 0.005;
  return `${sign}₦${abs.toLocaleString("en-NG", whole ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Short amount for chart axes and ring totals: ₦36.6M, ₦145K. */
export function compactNaira(value: number): string {
  return "₦" + new Intl.NumberFormat("en-NG", { notation: "compact", maximumFractionDigits: 1 }).format(value);
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
  if (days > 1 && days < 7) return d.toLocaleDateString("en-NG", { weekday: "long" });
  return d.toLocaleDateString("en-NG", { day: "numeric", month: "short" });
}

/** "14 Nov 2026". Accepts a Date, an ISO string or a saved "YYYY-MM-DD hh:mm" string. Empty for missing values. */
export function dateLabel(value: Date | string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }): string {
  const d = value instanceof Date ? value : typeof value === "string" ? parseSaved(value) ?? new Date(value) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString("en-NG", opts) : "";
}

/** "14 Nov, 2:30 PM" for activity and sales lists. */
export function dateTimeLabel(value: string | null | undefined): string {
  const d = parseSaved(value);
  return d ? d.toLocaleString("en-NG", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true }) : value ?? "";
}
