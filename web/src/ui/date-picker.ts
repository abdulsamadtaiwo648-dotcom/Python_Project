/** Shift a YYYY-MM-DD day by a number of days, using UTC so the server's and phone's time zones don't move it. */
export function shiftIso(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
}
