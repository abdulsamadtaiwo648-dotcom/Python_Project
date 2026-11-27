import EmptyState from "../components/EmptyState";
import { useEffect, useState, type FormEvent } from "react";
import { useToast } from "../ui/Toast";
import { useOpenNew } from "../ui/useOpenNew";
import { FilterChips } from "../ui";

// Short chip names for the money kinds. The values saved on the server are not changed.
const KIND_LABEL: Record<string, string> = {
  "Owner contribution": "Owner contribution",
  "Loan": "Loan",
  "Refund received": "Refund",
  "Other income": "Other",
};
import { ApiError, api } from "../api";
import { moneyInFor, moneyInTotal, MONEY_IN_KINDS, TRANSFER_KIND } from "../moneyIn";
import { canTransfer, hasOneAccount, pickableAccounts } from "../accounts";
import MonthPicker from "../components/MonthPicker";
import Sheet from "../components/Sheet";
import ImportSheet from "../components/ImportSheet";
import { useDashboardMonth } from "../dashboardMonth";
import { useData } from "../data";
import { money, relativeDay } from "../format";
import { monthNow, ymLabel } from "../month";
import { useSession } from "../session";
import { minEntryIso, todayIso } from "../offline";
import type { MoneyInItem } from "../types";

/** Money that is not a sale. It counts in cash flow and the cash balance, never in profit. */
export default function MoneyIn() {
  const { access } = useSession();
  const { moneyIn, reload } = useData();
  const dm = useDashboardMonth();
  const [editing, setEditing] = useState<MoneyInItem | "new" | null>(null);
  useOpenNew(() => setEditing("new"));
  const [importing, setImporting] = useState(false);
  // Rows deleted but not yet confirmed. They stay hidden until Undo or until the delete is sent.
  const [hidden, setHidden] = useState<Set<number>>(() => new Set());
  const toast = useToast();
  useEffect(() => { document.title = "Money in | SoloBiz"; }, []);

  const current = dm.current ?? monthNow();
  const ym = dm.selected ?? current;
  const year = ym.slice(0, 4);
  const monthRange = { kind: "month", ym } as const;
  const yearRange = { kind: "year", year } as const;
  const monthItems = moneyInFor(moneyIn, monthRange).filter((i) => !hidden.has(i.id));

  // Hide the row now; send the delete after five seconds. Undo brings the row back and sends nothing.
  function remove(item: MoneyInItem) {
    setHidden((h) => new Set(h).add(item.id));
    const timer = window.setTimeout(() => {
      api.del(`/api/money-in/${item.id}`)
        .then(() => reload())
        .catch(() => {
          setHidden((h) => { const n = new Set(h); n.delete(item.id); return n; });
          toast({ text: "Could not delete that money in. It is back in your list." });
        });
    }, 5000);
    toast({
      text: "Money in deleted.", actionLabel: "Undo",
      onAction: () => {
        window.clearTimeout(timer);
        setHidden((h) => { const n = new Set(h); n.delete(item.id); return n; });
      },
    });
  }

  return (
    <section className="tab-content page-stack" aria-labelledby="money-in-title">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="money-in-title">Money in</h2>
          <p className="page-sub">Owner capital, loans and refunds. This is not a sale, so it does not change sales totals or profit.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setImporting(true)}>Import CSV</button>
          <button type="button" className="sb-btn sb-btn-primary" onClick={() => setEditing("new")}>Record money in</button>
        </div>
      </div>

      <MonthPicker value={ym} current={current} months={dm.months} onChange={dm.setMonth} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" id="money-in-month-total">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Money in in {ymLabel(ym)}</p>
          <p className="stat-value text-slate-900">{money(moneyInTotal(moneyIn, monthRange))}</p>
          <p className="text-xs text-slate-500">{monthItems.length} {monthItems.length === 1 ? "entry" : "entries"}</p>
        </div>
        <div className="kpi-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" id="money-in-year-total">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Money in in {year}</p>
          <p className="stat-value text-slate-900">{money(moneyInTotal(moneyIn, yearRange))}</p>
          <p className="text-xs text-slate-500">The whole year up to the month shown or the year to date.</p>
        </div>
      </div>


      <div className="sb-panel">
        {monthItems.length === 0 ? (
          <EmptyState message={`No money in recorded for ${ymLabel(ym)}.`} action={<button type="button" className="sb-btn sb-btn-primary" onClick={() => setEditing("new")}>Record money in</button>} />
        ) : (
          <ul className="divide-y divide-slate-100" aria-label="Money in entries">
            {monthItems.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-900">{i.kind}</p>
                  <p className="truncate text-xs text-slate-500">{i.description || "No note"} · {relativeDay(i.entry_date || i.date)}</p>
                </div>
                <p className="text-sm font-semibold text-emerald-700">{money(i.amount)}</p>
                <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setEditing(i)}>Edit</button>
                {access?.is_owner && (
                  <button type="button" className="sb-btn sb-btn-danger-text" onClick={() => void remove(i)}>Delete</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {importing && <ImportSheet kind="money_in" onDone={() => void reload()} onClose={() => setImporting(false)} />}
      {editing && (
        <MoneyInForm initial={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void reload(); }} />
      )}
    </section>
  );
}

export function MoneyInForm(props: { initial?: MoneyInItem; defaultKind?: string; onClose: () => void; onSaved: () => void }) {
  const { initial } = props;
  const { accounts } = useData();
  const defaultId = accounts.find((a) => a.is_default)?.id ?? null;
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [kind, setKind] = useState(initial?.kind ?? props.defaultKind ?? MONEY_IN_KINDS[0]);
  const [accountId, setAccountId] = useState<number | null>(initial?.account_id ?? defaultId);
  const [fromId, setFromId] = useState<number | null>(null);
  const kinds = canTransfer(accounts) ? [...MONEY_IN_KINDS, TRANSFER_KIND] : MONEY_IN_KINDS;
  const isTransfer = kind === TRANSFER_KIND;
  const active = pickableAccounts(accounts, initial?.account_id);
  const [note, setNote] = useState(initial?.description ?? "");
  const [day, setDay] = useState(initial?.entry_date ?? todayIso());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const n = Number(amount.replace(/,/g, ""));
    if (!Number.isFinite(n) || n <= 0) return setError("Enter an amount greater than zero.");
    if (!day) return setError("Choose the date.");
    if (isTransfer && (fromId === null || fromId === accountId)) return setError("A transfer needs two different accounts: where the money came from, and where it went.");
    setBusy(true);
    setError("");
    const body = { amount: n, kind, description: note.trim(), entry_date: day, account_id: accountId,
      from_account_id: isTransfer ? fromId : null };
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
          <span className="ui-stat-label">What kind of money?</span>
          {/* Chips show short names; the stored kind values are unchanged. */}
          <FilterChips label="What kind of money?" value={kind} onChange={setKind}
            options={kinds.map((k) => ({ value: k, label: KIND_LABEL[k] ?? k }))} />
        </div>
        {isTransfer && (
          <div className="sb-field">
            <label htmlFor="money-in-from">Came from</label>
            <select id="money-in-from" required value={fromId ?? ""} onChange={(e) => setFromId(Number(e.target.value))}>
              <option value="" disabled>Choose an account</option>
              {active.filter((a) => !a.archived).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
        )}
        {!hasOneAccount(accounts) && (
          <div className="sb-field">
            <label htmlFor="money-in-account">{isTransfer ? "Went into" : "Received into"}</label>
            <select id="money-in-account" required value={accountId ?? ""} onChange={(e) => setAccountId(Number(e.target.value))}>
              {active.filter((a) => !a.archived).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
        )}
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
