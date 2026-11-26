import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import { isNairaAmount } from "../accounts";
import { useData } from "../data";
import { minEntryIso, todayIso } from "../offline";
import { money } from "../format";
import type { AccountView } from "../types";

export type { AccountView } from "../types";

/** Where the business's money is held. Owners add, rename, archive and choose the default. */
export default function Accounts() {
  const [accounts, setAccounts] = useState<AccountView[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const { reload } = useData();
  useEffect(() => { document.title = "Accounts | SoloBiz"; void load(); }, []);

  async function load() {
    try {
      const res = await api.get<{ accounts: AccountView[] }>("/api/accounts");
      setAccounts(res.accounts);
      setError("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load accounts. Check your connection.");
    } finally {
      setLoaded(true);
    }
  }

  async function change(account: AccountView, body: Record<string, unknown>) {
    try {
      await api.put(`/api/accounts/${account.id}`, body);
      setError("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Try again.");
    }
  }

  const active = accounts.filter((a) => !a.archived).length;

  return (
    <section className="tab-content page-stack" aria-labelledby="accounts-title">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="accounts-title">Accounts</h2>
          <p className="page-sub">Where your money is held: Cash, Bank, Petty Cash. Each business has one default account.</p>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="sb-panel">
        {!loaded ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          <ul className="divide-y divide-slate-100" aria-label="Accounts">
            {accounts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-semibold ${a.archived ? "text-slate-400 line-through" : "text-slate-900"}`}>{a.name}</p>
                  <p className="text-xs text-slate-500">
                    Opening {money(Number(a.opening_balance))} from {a.opening_date}
                    {a.is_default ? " · Default" : ""}{a.archived ? " · Archived" : ""}
                  </p>
                </div>
                {!a.archived && !a.is_default && (
                  <button type="button" className="sb-btn sb-btn-secondary" onClick={() => void change(a, { is_default: true })}>Make default</button>
                )}
                {!a.archived && !a.is_default && (
                  <button type="button" className="sb-btn sb-btn-secondary" onClick={() => void change(a, { archived: true })}>Archive</button>
                )}
                {a.archived && (
                  <button type="button" className="sb-btn sb-btn-secondary" onClick={() => void change(a, { archived: false })}>Restore</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <AddAccount onAdded={() => { void load(); void reload(); }} onError={setError} activeCount={active} />
    </section>
  );
}

function AddAccount(props: { onAdded: () => void; onError: (m: string) => void; activeCount: number }) {
  const [name, setName] = useState("");
  const [opening, setOpening] = useState("");
  const [day, setDay] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function save(e: FormEvent) {
    e.preventDefault();
    if (opening.trim() && !isNairaAmount(opening)) return props.onError("Enter the opening balance as an amount, for example 5000 or 5,000.50.");
    setBusy(true);
    try {
      await api.post("/api/accounts", { name: name.trim(), opening_balance: opening.trim(), opening_date: day });
      setName(""); setOpening(""); setDay("");
      setMessage("Account added.");
      props.onError("");
      props.onAdded();
    } catch (err) {
      props.onError(err instanceof ApiError ? err.message : "Could not add the account. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="sb-panel grid gap-3 sm:grid-cols-2" aria-label="Add an account">
      <h3 className="text-base font-bold text-slate-900 sm:col-span-2">Add an account</h3>
      <div className="sb-field">
        <label htmlFor="account-name">Name</label>
        <input id="account-name" type="text" maxLength={60} placeholder="e.g. Petty Cash or Bank" required value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="sb-field">
        <label htmlFor="account-opening">Opening balance (optional)</label>
        <input id="account-opening" type="text" inputMode="decimal" placeholder="0" value={opening} onChange={(e) => setOpening(e.target.value)} />
      </div>
      <div className="sb-field">
        <label htmlFor="account-day">Opening date (optional)</label>
        <input id="account-day" type="date" min={minEntryIso()} max={todayIso()} value={day} onChange={(e) => setDay(e.target.value)} />
        <p className="sb-help">Blank means the day you add the account. Money counts from this date, not before it.</p>
      </div>
      <div className="flex items-end justify-between gap-3 sm:col-span-2">
        <p role="status" className="text-xs text-emerald-700">{message}</p>
        <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{busy ? "Adding…" : "Add account"}</button>
      </div>
    </form>
  );
}
