import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import Sheet from "../components/Sheet";
import { useSession } from "../session";
import { money, parseSaved, relativeDay } from "../format";
import { minEntryIso, todayIso } from "../offline";

export interface MoneyInItem {
  id: number;
  amount: number;
  kind: string;
  description: string | null;
  date: string;
  entry_date: string;
}

const FALLBACK_KINDS = ["Owner's capital", "Loan received", "Refund received", "Other money in"];

/** Money that is not a sale. It is shown here only: it is not revenue and not profit. */
export default function MoneyIn() {
  const { access } = useSession();
  const [items, setItems] = useState<MoneyInItem[]>([]);
  const [kinds, setKinds] = useState<string[]>(FALLBACK_KINDS);
  const [editing, setEditing] = useState<MoneyInItem | "new" | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get<{ money_in: MoneyInItem[]; kinds: string[] }>("/api/money-in");
      setItems(res.money_in);
      setKinds(res.kinds);
      setError("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load money in. Check your connection.");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => { document.title = "Money in | SoloBiz"; void load(); }, [load]);

  const thisMonth = useMemo(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    return items.reduce((sum, i) => {
      const d = parseSaved(i.entry_date || i.date);
      return d && d >= start ? sum + i.amount : sum;
    }, 0);
  }, [items]);

  async function remove(item: MoneyInItem) {
    if (!window.confirm("Delete this money in? This cannot be undone.")) return;
    try {
      await api.del(`/api/money-in/${item.id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete. Try again.");
    }
  }

  return (
    <section className="tab-content page-stack" aria-labelledby="money-in-title">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="money-in-title">Money in</h2>
          <p className="page-sub">Owner capital, loans and refunds. This is not a sale, so it does not change sales totals or profit.</p>
        </div>
        <button type="button" className="sb-btn sb-btn-primary" onClick={() => setEditing("new")}>Record money in</button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Money in this month</p>
          <p className="stat-value text-slate-900">{money(thisMonth)}</p>
        </div>
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Entries</p>
          <p className="stat-value text-slate-900">{items.length}</p>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="sb-panel">
        {!loaded ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-500">No money in recorded yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100" aria-label="Money in entries">
            {items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-900">{i.kind}</p>
                  <p className="truncate text-xs text-slate-500">{i.description || "No note"} · {relativeDay(i.entry_date || i.date)}</p>
                </div>
                <p className="text-sm font-semibold text-slate-900">{money(i.amount)}</p>
                <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setEditing(i)}>Edit</button>
                {access?.is_owner && (
                  <button type="button" className="sb-btn sb-btn-danger-text" onClick={() => void remove(i)}>Delete</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <MoneyInForm kinds={kinds} initial={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />
      )}
    </section>
  );
}

function MoneyInForm(props: { kinds: string[]; initial?: MoneyInItem; onClose: () => void; onSaved: () => void }) {
  const { initial } = props;
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [kind, setKind] = useState(initial?.kind ?? props.kinds[0]);
  const [note, setNote] = useState(initial?.description ?? "");
  const [day, setDay] = useState(initial?.entry_date ?? todayIso());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const n = Number(amount.replace(/,/g, ""));
    if (!Number.isFinite(n) || n <= 0) return setError("Enter an amount greater than zero.");
    if (!day) return setError("Choose the date.");
    setBusy(true);
    setError("");
    const body = { amount: n, kind, description: note.trim(), entry_date: day };
    try {
      if (initial) await api.put(`/api/money-in/${initial.id}`, body);
      else await api.post("/api/money-in", body);
      props.onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Check your connection and try again.");
      setBusy(false);
    }
  }

  return (
    <Sheet title={initial ? "Edit money in" : "Record money in"} onClose={props.onClose} compact>
      <form onSubmit={save} className="sb-sheet-body">
        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
        <div className="sb-field">
          <label htmlFor="money-in-amount">Amount</label>
          <div className="sb-money">
            <span aria-hidden="true">₦</span>
            <input id="money-in-amount" type="text" inputMode="decimal" placeholder="0" required className="currency-input"
              value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
          </div>
        </div>
        <div className="sb-field">
          <label htmlFor="money-in-kind">What kind of money?</label>
          <select id="money-in-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {props.kinds.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div className="sb-field">
          <label htmlFor="money-in-day">Date</label>
          <input id="money-in-day" type="date" required value={day} min={minEntryIso()} max={todayIso()}
            onChange={(e) => setDay(e.target.value)} />
        </div>
        <div className="sb-field">
          <label htmlFor="money-in-note">Note (optional)</label>
          <input id="money-in-note" type="text" maxLength={200} placeholder="e.g. Loan from my brother" value={note}
            onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="sb-sheet-foot">
          <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose}>Cancel</button>
          <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Sheet>
  );
}
