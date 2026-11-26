/** Same rule as the server: an amount in naira with at most two decimals, commas allowed, no exponents. */
export function isNairaAmount(text: string): boolean {
  const s = text.trim().replace(/,/g, "");
  return /^-?\d+(\.\d{1,2})?$/.test(s) && s.replace("-", "").length > 0;
}

/** The opening balance the owner typed, or "0" when left blank. */
export function openingBalanceOrZero(text: string): string {
  return text.trim() === "" ? "0" : text.trim();
}
