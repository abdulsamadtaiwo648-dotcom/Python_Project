import { useEffect, useState } from "react";
import { api } from "./api";
import { todayIso } from "./offline";
import type { AccountView } from "./types";

/** Cash at hand: the balance of every active account, added together, as of today. Read from the
 * account statements, which already count each movement once. undefined = loading, null = unavailable. */
export function useCashAtHand(accounts: AccountView[], stamp: unknown): number | null | undefined {
  const [value, setValue] = useState<number | null | undefined>(undefined);
  useEffect(() => {
    const active = accounts.filter((a) => !a.archived);
    if (active.length === 0) { setValue(0); return; }
    let live = true;
    const anchor = todayIso();
    Promise.all(active.map((a) =>
      api.get<{ closing: { balance: string } }>(`/api/accounts/${a.id}/statement?period=month&date=${anchor}`)))
      .then((results) => {
        if (live) setValue(results.reduce((sum, r) => sum + Math.round(Number(r.closing.balance) * 100), 0) / 100);
      })
      .catch(() => { if (live) setValue(null); });
    return () => { live = false; };
  }, [accounts, stamp]);
  return value;
}
