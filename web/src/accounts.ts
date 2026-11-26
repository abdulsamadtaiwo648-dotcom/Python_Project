/** Same rule as the server: an amount in naira with at most two decimals, commas allowed, no exponents. */
export function isNairaAmount(text: string): boolean {
  const s = text.trim().replace(/,/g, "");
  return /^-?\d+(\.\d{1,2})?$/.test(s) && s.replace("-", "").length > 0;
}

/** The opening balance the owner typed, or "0" when left blank. */
export function openingBalanceOrZero(text: string): string {
  return text.trim() === "" ? "0" : text.trim();
}

/** The accounts an entry can use: active ones, plus the entry's own account if it is archived. */
export function pickableAccounts<T extends { id: number; archived: boolean }>(accounts: T[], currentId?: number | null): T[] {
  return accounts.filter((a) => !a.archived || a.id === currentId);
}

/** With one active account there is nothing to choose, so selectors are hidden. */
export function hasOneAccount(accounts: { archived: boolean }[]): boolean {
  return accounts.filter((a) => !a.archived).length <= 1;
}

/** A transfer needs two active accounts. */
export function canTransfer(accounts: { archived: boolean }[]): boolean {
  return accounts.filter((a) => !a.archived).length >= 2;
}
