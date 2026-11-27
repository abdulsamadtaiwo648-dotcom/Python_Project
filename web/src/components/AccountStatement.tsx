import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { lineLabel, overspentLine, periodLabel, type StatementPeriod } from "../statement";
import { money, relativeDay } from "../format";
import { DayGroup, ListRow } from "../ui";
import { todayIso } from "../offline";
import type { AccountView } from "../types";

interface Line { date: string; direction: "in" | "out"; amount: string; label: string; source: string; counterpart: string | null; approximate: boolean; ref: number | null }
export interface StatementData {
  account: AccountView;
  period: { kind: StatementPeriod; start: string; end: string; previous_anchor: string; next_anchor: string };
  opening: { balance: string };
  receipts: { total: string; items: Line[] };
  payments: { total: string; items: Line[] };
  closing: { balance: string; overspent: string | null };
}

/** One account for a week or a month: four figures, then every entry. */
export default function AccountStatement({ account }: { account: AccountView }) {
  const [kind, setKind] = useState<StatementPeriod>("month");
  const [anchor, setAnchor] = useState(todayIso());
  const [data, setData] = useState<StatementData | null>(null);
  const [error, setError] = useState("");

  // Start again on the current period whenever a different account is chosen.
  useEffect(() => { setAnchor(todayIso()); setData(null); }, [account.id]);

  useEffect(() => {
    let live = true;
    api.get<StatementData>(`/api/accounts/${account.id}/statement?period=${kind}&date=${anchor}`)
      .then((res) => { if (live) { setData(res); setError(""); } })
      .catch((err) => { if (live) setError(err instanceof ApiError ? err.message : "Could not load this account. Check your connection."); });
    return () => { live = false; };
  }, [account.id, kind, anchor]);

  const closing = data ? Number(data.closing.balance) : 0;
  const overdrawn = closing < 0;
  const overspent = overspentLine(data?.closing.overspent);
  const entries = data ? [...data.receipts.items, ...data.payments.items].sort((a, b) => b.date.localeCompare(a.date)) : [];
  // Entries grouped by day, newest day first, each with that day's net movement.
  const dayGroups = entries.reduce<{ date: string; items: Line[]; net: number }[]>((groups, item) => {
    const last = groups[groups.length - 1];
    const signed = (item.direction === "in" ? 1 : -1) * Number(item.amount);
    if (last && last.date === item.date) { last.items.push(item); last.net += signed; }
    else groups.push({ date: item.date, items: [item], net: signed });
    return groups;
  }, []);

  return (
    <section className="space-y-4" aria-labelledby="statement-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="statement-title" className="text-base font-bold text-slate-900">{account.name}</h3>
        <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Period">
          {(["week", "month"] as const).map((k) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${kind === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
              {k === "week" ? "Week" : "Month"}
            </button>
          ))}
        </div>
      </div>

      {data && (
        <div className="flex items-center justify-between gap-2">
          <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" aria-label="Previous period" onClick={() => setAnchor(data.period.previous_anchor)}>◀</button>
          <p className="text-sm font-semibold text-slate-800">{periodLabel(kind, data.period.start, data.period.end)}</p>
          <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" aria-label="Next period" onClick={() => setAnchor(data.period.next_anchor)}>▶</button>
        </div>
      )}

      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      {!data && !error && <div className="h-44 animate-pulse rounded-2xl bg-slate-100" aria-hidden="true" />}

      {data && (
        <>
          <dl className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <Row label="Opening" value={money(Number(data.opening.balance))} />
            <Row label="Received" value={`+${money(Number(data.receipts.total))}`} tone="text-emerald-700" />
            <Row label="Spent" value={`−${money(Number(data.payments.total))}`} tone="text-slate-800" />
            <div className="flex items-center justify-between gap-3 bg-slate-50 px-4 py-3">
              <dt className="text-sm font-semibold text-slate-900">Closing</dt>
              <dd className="text-right">
                <span className={`block text-lg font-bold tabular-nums ${overdrawn ? "text-amber-700" : "text-slate-900"}`}>{money(closing)}</span>
                {overdrawn && overspent && <span className="block text-xs font-semibold text-amber-700">Overspent{overspent.replace("Overspent by", " by")}</span>}
              </dd>
            </div>
          </dl>

          <div>
            <h4 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Entries</h4>
            {entries.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">No entries in this period.</p>
            ) : (
              <div>
                {dayGroups.map((g) => (
                  <DayGroup key={g.date} label={relativeDay(g.date)} total={`${g.net < 0 ? "−" : "+"}${money(Math.abs(g.net))}`}>
                    {g.items.map((i, n) => (
                      <ListRow key={`${i.date}-${i.source}-${i.ref ?? n}`}
                        title={`${lineLabel(i)}${i.approximate ? " (approx.)" : ""}`}
                        subtitle={i.counterpart ?? undefined}
                        amount={`${i.direction === "in" ? "+" : "−"}${money(Number(i.amount))}`}
                        tone={i.direction === "in" ? "money-in" : undefined} />
                    ))}
                  </DayGroup>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Row({ label, value, tone = "text-slate-900" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className={`text-sm font-semibold tabular-nums ${tone}`}>{value}</dd>
    </div>
  );
}
