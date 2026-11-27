import Skeleton from "../components/Skeleton";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api";
import { UpgradeNotice } from "../components/Upgrade";
import Sheet from "../components/Sheet";
import CategoriesSheet from "../components/CategoriesSheet";
import ImportSheet from "../components/ImportSheet";
import { useExpenseCategories } from "../categories";
import { hasOneAccount, pickableAccounts } from "../accounts";
import { useData } from "../data";
import { useDashboardMonth } from "../dashboardMonth";
import { money } from "../format";
import { dayOf } from "../analytics";
import { monthNow, ymLabel } from "../month";
import MonthPicker from "../components/MonthPicker";
import { dayStamp, minEntryIso, nextTempId, todayIso } from "../offline";
import { useToast } from "../ui/Toast";
import { DayGroup, ListRow, SelectSheet } from "../ui";
import type { Expense } from "../types";

const toAmount = (v: string) => Number(v.replace(/,/g, ""));

function ExpenseForm(props: { initial?: Expense; onClose: () => void }) {
  const { initial } = props;
  const { write, accounts } = useData();
  const toast = useToast();
  const defaultAccountId = accounts.find((a) => a.is_default)?.id ?? null;
  const [accountId, setAccountId] = useState<number | null>(initial?.account_id ?? defaultAccountId);
  const cats = useExpenseCategories();
  // A category is pickable if it is active, or if this expense already uses it (even when archived).
  const pickable = cats.all.filter((c) => !c.archived || c.name === initial?.category).map((c) => c.name);
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [entryDay, setEntryDay] = useState(initial?.entry_date ?? todayIso());
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const addAnother = useRef(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const again = addAnother.current && !initial;
    addAnother.current = false;
    const n = toAmount(amount);
    if (!Number.isFinite(n) || n <= 0) return setError("Enter an amount greater than zero.");
    if (!category || !description.trim()) return setError("Choose a category and say what it was for.");
    if (!entryDay) return setError("Choose the date of this expense.");
    setBusy(true);
    setError("");
    try {
      const body = { amount: n, category, description: description.trim(), entry_date: entryDay, account_id: accountId };
      if (initial) {
        await write({ kind: "expense_edit", method: "PUT", url: `/api/expenses/${initial.server_id}`, body,
          meta: { expenseId: initial.server_id, patch: { ...body, date: dayStamp(entryDay) } } });
      } else {
        const expense: Expense = { server_id: nextTempId(), ...body, date: dayStamp(entryDay), synced: false };
        await write({ kind: "expense_add", method: "POST", url: "/add", body, meta: { expense } });
      }
      if (again) {
        // Keep the date and category; start the next expense.
        setAmount("");
        setDescription("");
        setNotice("Saved. Add the next one.");
        document.getElementById("expense-amount")?.focus();
        return;
      }
      props.onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Try again.");
    } finally {
      setBusy(false);
    }
  }

  // Delete now, with Undo for five seconds instead of a confirm popup. The request is sent when the window closes.
  function remove() {
    if (!initial) return;
    const expenseId = initial.server_id;
    const timer = window.setTimeout(() => {
      void write({ kind: "expense_delete", method: "DELETE", url: `/api/expenses/${expenseId}`, meta: { expenseId } })
        .catch(() => toast({ text: "Could not delete that expense. It is back in your list." }));
    }, 5000);
    toast({ text: "Expense deleted.", actionLabel: "Undo", onAction: () => window.clearTimeout(timer) });
    props.onClose();
  }

  return (
    <Sheet title={initial ? "Edit expense" : "Add expense"} onClose={props.onClose} compact>
      <form onSubmit={save} className="sb-sheet-body">
        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
        {notice && <p role="status" className="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">{notice}</p>}
        <div className="sb-field">
          <label htmlFor="expense-amount">Amount</label>
          <div className="sb-money">
            <span aria-hidden="true">₦</span>
            <input id="expense-amount" type="text" inputMode="decimal" placeholder="0" required className="currency-input text-3xl font-bold tabular-nums"
              value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
          </div>
        </div>
        <div className="sb-field">
          <label htmlFor="expense-day">Date</label>
          <input id="expense-day" type="date" required value={entryDay} min={minEntryIso()} max={todayIso()}
            onChange={(e) => setEntryDay(e.target.value)} />
          <p className="sb-help">The day this expense belongs to. Up to two years back; not in the future.</p>
        </div>
        <div className="sb-field">
          <SelectSheet label="Category" value={category} placeholder="Choose a category"
            options={pickable.map((c) => ({ value: c, label: c }))} onChange={setCategory} />
        </div>
        <div className="sb-field">
          <label htmlFor="expense-description">What was it for?</label>
          <input id="expense-description" type="text" placeholder="e.g. Generator fuel" required value={description}
            onChange={(e) => setDescription(e.target.value)} />
        </div>
        {!hasOneAccount(accounts) && (
          <div className="sb-field">
            <SelectSheet label="Paid from" placeholder="Choose an account"
              value={accountId === null ? "" : String(accountId)}
              options={pickableAccounts(accounts, initial?.account_id).map((a) => ({
                value: String(a.id), label: `${a.name}${a.archived ? " (archived)" : ""}${a.is_default ? " · default" : ""}`,
              }))}
              onChange={(v) => setAccountId(Number(v))} />
          </div>
        )}
        <div className="sb-sheet-foot">
          {initial ? (
            <>
              <button type="button" className="sb-btn sb-btn-danger-text" onClick={remove} disabled={busy}>Delete</button>
              <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose}>Cancel</button>
              <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>Save changes</button>
            </>
          ) : (
            <>
              <button type="submit" className="sb-btn sb-btn-secondary" disabled={busy}
                onClick={() => { addAnother.current = true; }}>Save and add another</button>
              <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{busy ? "Saving…" : "Save expense"}</button>
            </>
          )}
        </div>
      </form>
    </Sheet>
  );
}

export default function Expenses() {
  const { expenses, subscription, reload, accounts, loading } = useData();
  const dm = useDashboardMonth();
  const cats = useExpenseCategories();
  const [managing, setManaging] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState<Expense | "new" | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [account, setAccount] = useState("");
  const [exact, setExact] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => { document.title = "Expenses | SoloBiz"; }, []);

  const ym = dm.selected ?? monthNow();
  const monthName = ymLabel(ym);
  const current = dm.current ?? monthNow();
  // The month total is the same figure Home shows, so the two always agree.
  const monthTotal = dm.summary?.month_expenses ?? 0;
  const dateRange = Boolean(from || to);
  const inScope = dateRange
    ? expenses.filter((e) => (!from || dayOf(e) >= from) && (!to || dayOf(e) <= to))
    : expenses.filter((e) => dayOf(e).startsWith(ym));
  const visible = inScope.filter((e) =>
    (!category || e.category === category) && (!account || String(e.account_id) === account) &&
    (!exact || Math.abs(e.amount - Number(exact)) < 0.005));
  const filterCount = [category, account, exact, from || to].filter(Boolean).length;
  const accountName = (id: number | null | undefined) => accounts.find((a) => a.id === id)?.name;
  const showAccounts = !hasOneAccount(accounts);

  // Group by day, newest day first.
  const days = useMemo(() => {
    const map = new Map<string, Expense[]>();
    for (const e of visible) {
      const d = dayOf(e);
      map.set(d, [...(map.get(d) ?? []), e]);
    }
    return [...map.entries()]
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([day, items]) => ({ day, items: items.sort((a, b) => (b.server_id ?? 0) - (a.server_id ?? 0)), total: items.reduce((s, e) => s + e.amount, 0) }));
  }, [visible]);

  function clearFilters() { setCategory(""); setAccount(""); setExact(""); setFrom(""); setTo(""); }

  return (
    <section id="tab-expenses-content" className="tab-content page-stack" aria-labelledby="expenses-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="page-title" id="expenses-title">Expenses</h2>
        <MonthPicker value={ym} current={current} months={dm.months} onChange={dm.setMonth} />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-xs font-medium text-slate-500">Spent in {monthName}</p>
        <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{money(monthTotal)}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" id="btn-new-expense" className="sb-btn sb-btn-primary flex-1 justify-center" onClick={() => setEditing("new")}>
            Add expense
          </button>
          <button type="button" className="sb-btn sb-btn-secondary" aria-expanded={filterOpen} aria-controls="expense-filter-panel" onClick={() => setFilterOpen(true)}>
            Filter{filterCount > 0 ? ` (${filterCount})` : ""}
          </button>
        </div>
      </div>

      {subscription?.current.history_days != null && (
        <UpgradeNotice title={`Showing the last ${subscription.current.history_days} days of expenses`}
          text="Older expenses are kept safely. A longer history comes with a paid plan." plan="Basic" />
      )}

      {(filterCount > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <span>{dateRange ? `Showing ${from || "the start"} to ${to || "today"}` : `Filtered · ${visible.length} of ${inScope.length}`}</span>
          <button type="button" className="sb-link" onClick={clearFilters}>Clear filters</button>
        </div>
      )}

      {filterOpen && (
        <Sheet title="Filter expenses" onClose={() => setFilterOpen(false)}>
          <div id="expense-filter-panel" className="space-y-4 p-1">
            <div className="sb-field">
              <label htmlFor="filter-category">Category</label>
              <select id="filter-category" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {cats.all.map((c) => <option key={c.id} value={c.name}>{c.name}{c.archived ? " (archived)" : ""}</option>)}
              </select>
            </div>
            {showAccounts && (
              <div className="sb-field">
                <label htmlFor="filter-account">Paid from</label>
                <select id="filter-account" value={account} onChange={(e) => setAccount(e.target.value)}>
                  <option value="">All accounts</option>
                  {accounts.map((a) => <option key={a.id} value={String(a.id)}>{a.name}{a.archived ? " (archived)" : ""}</option>)}
                </select>
              </div>
            )}
            <div className="sb-field">
              <label htmlFor="filter-amount-exact">Exact amount (₦)</label>
              <input id="filter-amount-exact" type="number" min={0} step="any" inputMode="decimal" placeholder="Any"
                value={exact} onChange={(e) => setExact(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="sb-field">
                <label htmlFor="filter-from">From</label>
                <input id="filter-from" type="date" value={from} min={minEntryIso()} max={todayIso()} onChange={(e) => setFrom(e.target.value)} />
              </div>
              <div className="sb-field">
                <label htmlFor="filter-to">To</label>
                <input id="filter-to" type="date" value={to} min={minEntryIso()} max={todayIso()} onChange={(e) => setTo(e.target.value)} />
              </div>
            </div>
            <div className="sb-sheet-foot">
              <button type="button" className="sb-btn sb-btn-secondary" onClick={clearFilters}>Clear</button>
              <button type="button" className="sb-btn sb-btn-primary" onClick={() => setFilterOpen(false)}>Show expenses</button>
            </div>
          </div>
        </Sheet>
      )}

      <div id="transaction-list" className="space-y-5">
        {loading && expenses.length === 0 && <Skeleton rows={4} label="Loading expenses" />}
        {!loading && inScope.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <p className="text-sm text-slate-600">{dateRange ? "No expenses in these dates." : `No expenses in ${monthName}.`}</p>
            <button type="button" className="sb-btn sb-btn-primary mt-3" onClick={() => setEditing("new")}>Add one</button>
          </div>
        )}
        {inScope.length > 0 && visible.length === 0 && <p className="text-center text-sm text-slate-500">No expenses match your filter.</p>}
        {days.map((g) => (
          <DayGroup key={g.day} label={dayHeading(g.day)} total={money(g.total)}>
            {g.items.map((e) => (
              <ListRow key={e.server_id}
                ariaLabel={`Edit expense: ${e.category}, ${money(e.amount)}`}
                onClick={() => setEditing(e)}
                title={e.description || "No description"}
                chips={<>
                  <span>{e.category || "Other"}</span>
                  {showAccounts && accountName(e.account_id) && <span>{accountName(e.account_id)}</span>}
                  {!e.synced && <span className="sync-badge">Not synced</span>}
                </>}
                amount={money(e.amount)} />
            ))}
          </DayGroup>
        ))}
      </div>

      <div className="flex flex-wrap justify-center gap-4 pt-2 text-xs font-semibold text-slate-500">
        <button type="button" className="hover:text-slate-800" onClick={() => setManaging(true)}>Categories</button>
        <button type="button" className="hover:text-slate-800" onClick={() => setImporting(true)}>Import CSV</button>
        <Link to="/reports" className="hover:text-slate-800">Reports</Link>
      </div>

      {editing && (
        <ExpenseForm initial={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />
      )}
      {importing && <ImportSheet kind="expenses" onDone={() => void reload()} onClose={() => setImporting(false)} />}
      {managing && <CategoriesSheet categories={cats.all} onChanged={() => void cats.reload()} onClose={() => setManaging(false)} />}
    </section>
  );
}

/** "Mon 12 Jan" for a YYYY-MM-DD business day. */
function dayHeading(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  if (!y) return day;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}
