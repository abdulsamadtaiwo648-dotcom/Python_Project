import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { lineLabel, overspentLine, periodLabel, type StatementPeriod } from "../statement";
import { money } from "../format";
import { todayIso } from "../offline";
import type { AccountView } from "../types";

interface Line { date: string; direction: "in" | "out"; amount: string; label: string; source: string; counterpart: string | null; approximate: boolean }
interface StatementData {
  account: AccountView;
  period: { kind: StatementPeriod; start: string; end: string; previous_anchor: string; next_anchor: string };
  opening: { balance: string; starting_balance: string; starting_balance_in_period: string; activity_before: string; starting_balance_date: string | null };
  receipts: { total: string; items: Line[] };
  payments: { total: string; items: Line[] };
  closing: { balance: string; overspent: string | null };
}

/** One account for a week (Monday to Sunday) or a month. Each figure opens to show where it comes from. */
export default function AccountStatement({ accounts }: { accounts: AccountView[] }) {
  const defaultId = accounts.find((a) => a.is_default)?.id ?? accounts[0]?.id;
  const [accountId, setAccountId] = useState<number | undefined>(defaultId);
  const [kind, setKind] = useState<StatementPeriod>("week");
  const [anchor, setAnchor] = useState(todayIso());
  const [data, setData] = useState<StatementData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (accountId === undefined && defaultId !== undefined) setAccountId(defaultId);
  }, [defaultId, accountId]);

  useEffect(() => {
    if (accountId === undefined) return;
    let live = true;
    api.get<StatementData>(`/api/accounts/${accountId}/statement?period=${kind}&date=${anchor}`)
      .then((res) => { if (live) { setData(res); setError(""); } })
      .catch((err) => { if (live) setError(err instanceof ApiError ? err.message : "Could not load this account. Check your connection."); });
    return () => { live = false; };
  }, [accountId, kind, anchor]);

  const overspent = overspentLine(data?.closing.overspent);

  return (
    <section className="sb-panel space-y-4" aria-labelledby="statement-title">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 id="statement-title" className="text-base font-bold text-slate-900">Account statement</h3>
          {data && <p className="text-xs text-slate-500">{data.account.name} · {periodLabel(kind, data.period.start, data.period.end)}</p>}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="sb-field">
            <label htmlFor="statement-account">Account</label>
            <select id="statement-account" value={accountId ?? ""} onChange={(e) => setAccountId(Number(e.target.value))}>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.archived ? " (archived)" : ""}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Period">
            {(["week", "month"] as const).map((k) => (
              <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${kind === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
                {k === "week" ? "Week" : "Month"}
              </button>
            ))}
          </div>
          {data && (
            <div className="flex items-center gap-1">
              <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" aria-label="Previous period" onClick={() => setAnchor(data.period.previous_anchor)}>◀</button>
              <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" aria-label="Next period" onClick={() => setAnchor(data.period.next_anchor)}>▶</button>
              {anchor !== todayIso() && <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={() => setAnchor(todayIso())}>This {kind}</button>}
            </div>
          )}
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Figure title="Opening balance" value={data.opening.balance}>
              <p>Starting balance: {money(Number(data.opening.starting_balance))}{data.opening.starting_balance_date ? ` from ${data.opening.starting_balance_date}` : ""}</p>
              {Number(data.opening.starting_balance_in_period) !== 0 && <p>Starting balance dated in this period: {money(Number(data.opening.starting_balance_in_period))}</p>}
              <p>Activity before this period: {money(Number(data.opening.activity_before))}</p>
            </Figure>
            <Figure title="Receipts" value={data.receipts.total} tone="text-emerald-700">
              <Lines items={data.receipts.items} empty="No receipts in this period." />
            </Figure>
            <Figure title="Payments" value={data.payments.total} tone="text-rose-700">
              <Lines items={data.payments.items} empty="No payments in this period." />
            </Figure>
            <Figure title="Closing balance" value={data.closing.balance} tone={Number(data.closing.balance) < 0 ? "text-rose-700" : "text-slate-900"}>
              <p>{money(Number(data.opening.balance))} + {money(Number(data.receipts.total))} − {money(Number(data.payments.total))} = {money(Number(data.closing.balance))}</p>
              {overspent && <p className="font-semibold text-rose-700">{overspent}</p>}
            </Figure>
          </div>
        </>
      )}
    </section>
  );
}

function Figure({ title, value, tone = "text-slate-900", children }: { title: string; value: string; tone?: string; children: React.ReactNode }) {
  return (
    <details className="rounded-xl border border-slate-200 bg-white p-3">
      <summary className="cursor-pointer list-none">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{title}</p>
        <p className={`mt-1 text-base font-bold ${tone}`}>{money(Number(value))}</p>
      </summary>
      <div className="mt-2 space-y-1 text-xs text-slate-600">{children}</div>
    </details>
  );
}

function Lines({ items, empty }: { items: Line[]; empty: string }) {
  if (items.length === 0) return <p>{empty}</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((i, n) => (
        <li key={`${i.date}-${n}`} className="flex items-center justify-between gap-2 py-1">
          <span className="min-w-0 truncate">{i.date} · {lineLabel(i)}{i.approximate ? " (approx.)" : ""}</span>
          <span className="flex-shrink-0 font-semibold text-slate-800">{money(Number(i.amount))}</span>
        </li>
      ))}
    </ul>
  );
}
