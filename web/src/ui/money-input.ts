/**
 * Money typing: "1250000" shows as "1,250,000", and up to two decimals are kept.
 * Only the display changes. The value the server receives is parsed by parseMoneyInput.
 */
export function formatMoneyInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const dot = cleaned.indexOf(".");
  const whole = (dot === -1 ? cleaned : cleaned.slice(0, dot)).replace(/^0+(?=\d)/, "");
  const decimals = dot === -1 ? null : cleaned.slice(dot + 1).replace(/\./g, "").slice(0, 2);
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (decimals === null) return grouped;
  return `${grouped || "0"}.${decimals}`;
}

/** Returns the naira amount, or null when the field is empty or not a number. */
export function parseMoneyInput(display: string): number | null {
  const cleaned = display.replace(/,/g, "");
  if (cleaned === "" || cleaned === ".") return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}
