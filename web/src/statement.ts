import { money } from "./format";

export type StatementPeriod = "week" | "month";

/** "12 – 18 Jan 2026" for a week, "January 2026" for a month. Dates are business days (UTC-stable). */
export function periodLabel(kind: StatementPeriod, start: string, end: string): string {
  const fmt = (iso: string, opts: Intl.DateTimeFormatOptions) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-NG", { timeZone: "UTC", ...opts });
  };
  if (kind === "month") return fmt(start, { month: "long", year: "numeric" });
  return `${fmt(start, { day: "numeric", month: "short" })} – ${fmt(end, { day: "numeric", month: "short", year: "numeric" })}`;
}

/** "Overspent by ₦5,000.00" when the closing balance is negative, otherwise null. */
export function overspentLine(overspent: string | null | undefined): string | null {
  return overspent ? `Overspent by ${money(Number(overspent))}` : null;
}

/** The transfer label for a line: "Transfer from Cash", "Transfer to Bank", or the plain label. */
export function lineLabel(item: { source: string; label: string; counterpart: string | null; direction: string }): string {
  if (item.source === "transfer_in") return `Transfer from ${item.counterpart ?? "another account"}`;
  if (item.source === "transfer_out") return `Transfer to ${item.counterpart ?? "another account"}`;
  return item.label;
}
