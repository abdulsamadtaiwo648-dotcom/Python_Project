import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import { isNairaAmount } from "../accounts";
import AccountStatement from "../components/AccountStatement";
import Sparkline from "../components/Sparkline";
import { useData } from "../data";
import { money } from "../format";
import { minEntryIso, todayIso } from "../offline";
import type { AccountView } from "../types";

/** Accounts: a card per account with its balance and recent trend. Tap one to see its statement. */
export default function Accounts() {
  const { accounts, reload } = useData();
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const active = accounts.filter((a) => !a.archived);
  const chosen = accounts.find((a) => a.id === selected) ?? active[0] ?? null;

  return (
    <section className="space-y-5" aria-labelledby="accounts-title">
      <h2 id="accounts-title" className="sr-only">Accounts</h2>
      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</p>}

      {active.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">No accounts yet.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {active.map((a) => (
            <AccountCard key={a.id} account={a} selected={chosen?.id === a.id} onSelect={() => setSelected(a.id)} />
          ))}
        </div>
      )}

      {chosen && <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5"><AccountStatement account={chosen} /></div>}

      <details className="rounded-2xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-800">Manage accounts</summary>
        <div className="mt-4 space-y-4">
          <ManageList accounts={accounts} onChange={() => void reload()} onError={setError} />
          <AddAccount onAdded={() => { setNotice("Account added."); void reload(); }} onError={setError} />
        </div>
      </details>
    </section>
  );
}

/** A card: name, balance (amber with "Overspent" when negative), and a six-month trend. */
function AccountCard({ account, selected, onSelect }: { account: AccountView; selected: boolean; onSelect: () => void }) {
  const [trend, setTrend] = useState<number[]>([]);
  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    const now = new Date();
    const anchors = Array.from({ length: 6 }, (_, i) =>
      new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - (5 - i), 15)).toISOString().slice(0, 10));
    Promise.all(anchors.map((d) =>
      api.get<{ closing: { balance: string } }>(`/api/accounts/${account.id}/statement?period=month&date=${d}`)))
      .then((rs) => {
        if (!live) return;
        const values = rs.map((r) => Number(r.closing.balance));
        setTrend(values);
        setBalance(values[values.length - 1]);
      })
      .catch(() => { if (live) setBalance(null); });
    return () => { live = false; };
  }, [account.id]);

  const overdrawn = balance !== null && balance < 0;
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected}
      className={`w-full rounded-2xl border bg-white p-4 text-left shadow-sm transition ${selected ? "border-blue-600 ring-1 ring-blue-600" : "border-slate-200 hover:border-slate-300"}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-semibold text-slate-900">{account.name}</p>
        {account.is_default && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">Default</span>}
      </div>
      {balance === null ? (
        <div className="mt-2 h-7 w-28 animate-pulse rounded bg-slate-100" aria-hidden="true" />
      ) : (
        <p className={`mt-1 text-2xl font-bold tabular-nums ${overdrawn ? "text-amber-700" : "text-slate-900"}`}>{money(balance)}</p>
      )}
      {overdrawn && <p className="text-xs font-semibold text-amber-700">Overspent</p>}
      <div className="mt-2">
        {trend.length > 0 && <Sparkline values={trend} label={`${account.name} balance over six months`} />}
      </div>
    </button>
  );
}

function ManageList(props: { accounts: AccountView[]; onChange: () => void; onError: (m: string) => void }) {
  async function change(account: AccountView, body: Record<string, unknown>) {
    try {
      await api.put(`/api/accounts/${account.id}`, body);
      props.onError("");
      props.onChange();
    } catch (err) {
      props.onError(err instanceof ApiError ? err.message : "Could not save. Try again.");
    }
  }
  return (
    <ul className="divide-y divide-slate-100" aria-label="Accounts">
      {props.accounts.map((a) => (
        <li key={a.id} className="flex flex-wrap items-center gap-3 py-3">
          <div className="min-w-0 flex-1">
            <p className={`text-sm font-medium ${a.archived ? "text-slate-400 line-through" : "text-slate-900"}`}>{a.name}</p>
            <p className="text-xs text-slate-500">
              Opening {money(Number(a.opening_balance))} from {a.opening_date}
              {a.is_default ? " · Default" : ""}{a.archived ? " · Archived" : ""}
            </p>
          </div>
          {!a.archived && !a.is_default && <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={() => void change(a, { is_default: true })}>Make default</button>}
          {!a.archived && !a.is_default && <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={() => void change(a, { archived: true })}>Archive</button>}
          {a.archived && <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={() => void change(a, { archived: false })}>Restore</button>}
        </li>
      ))}
    </ul>
  );
}

function AddAccount(props: { onAdded: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState("");
  const [opening, setOpening] = useState("");
  const [day, setDay] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (opening.trim() && !isNairaAmount(opening)) return props.onError("Enter the opening balance as an amount, for example 5000 or 5,000.50.");
    setBusy(true);
    try {
      await api.post("/api/accounts", { name: name.trim(), opening_balance: opening.trim(), opening_date: day });
      setName(""); setOpening(""); setDay("");
      props.onError("");
      props.onAdded();
    } catch (err) {
      props.onError(err instanceof ApiError ? err.message : "Could not add the account. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="grid gap-3 sm:grid-cols-2" aria-label="Add an account">
      <h3 className="text-sm font-semibold text-slate-900 sm:col-span-2">Add an account</h3>
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
        <p className="sb-help">Blank means the day you add the account.</p>
      </div>
      <div className="flex items-end justify-end sm:col-span-2">
        <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{busy ? "Adding…" : "Add account"}</button>
      </div>
    </form>
  );
}
