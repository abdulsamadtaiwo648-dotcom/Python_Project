import { useEffect, useState } from "react";
import { api } from "../api";
import { dateLabel, money, parseSaved } from "../format";
import { ListRow } from "../ui/ListRow";
import { ActionSheet, FAB } from "../ui";
import { useNavigate, useSearchParams } from "react-router-dom";
import { canTransfer } from "../accounts";
import { canUse } from "../access";
import { useData } from "../data";
import { useSession } from "../session";
import Accounts from "./Accounts";
import MoneyIn, { MoneyInForm } from "./MoneyIn";
import InfoTip from "../components/InfoTip";

type Tab = "accounts" | "moneyin" | "transfers";

/** Money: accounts, money in, and transfers between accounts, one page with tabs. */
export default function Money() {
  const { access } = useSession();
  const showAccounts = canUse(access, "accounts");
  const tabs: Tab[] = showAccounts ? ["accounts", "moneyin", "transfers"] : ["moneyin", "transfers"];
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [addOpen, setAddOpen] = useState(false);
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = requested && tabs.includes(requested) ? requested : tabs[0];
  const labels: Record<Tab, string> = { accounts: "Accounts", moneyin: "Money in", transfers: "Transfers" };

  return (
    <section className="tab-content page-stack" aria-labelledby="money-title">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="money-title">Money</h2>
        </div>
      </div>
      <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Money sections">
        {tabs.map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setParams({ tab: t })}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>
            {labels[t]}
          </button>
        ))}
      </div>
      {tab === "accounts" && <Accounts />}
      {tab === "moneyin" && <MoneyIn />}
      {tab === "transfers" && <Transfers onAddAccount={() => setParams({ tab: "accounts" })} />}
      <FAB label="Add money in or a transfer" onClick={() => setAddOpen(true)} />
      {addOpen && (
        <ActionSheet title="Add to money" onClose={() => setAddOpen(false)} options={[
          { label: "Money in", sub: "Owner contribution, loan, refund or other income", onSelect: () => navigate("/money?tab=moneyin&new=1") },
          { label: "Transfer", sub: "Move money from one account to another", onSelect: () => navigate("/money?tab=transfers") },
        ]} />
      )}
    </section>
  );
}

interface TransferItem { id: number; amount: number; description: string; entry_date: string; from_account_id: number | null; to_account_id: number | null }

function Transfers(props: { onAddAccount: () => void }) {
  const { accounts } = useData();
  const [open, setOpen] = useState(false);
  const [transfers, setTransfers] = useState<TransferItem[] | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    api.get<{ transfers: TransferItem[] }>("/api/transfers")
      .then((r) => { if (live) setTransfers(r.transfers); })
      .catch(() => { if (live) setTransfers([]); });
    return () => { live = false; };
  }, [revision]);
  const nameOf = (id: number | null) => accounts.find((a) => a.id === id)?.name ?? "Deleted account";
  if (!canTransfer(accounts)) {
    return (
      <div className="sb-panel flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600"><span>Why two accounts?</span> <InfoTip label="Why two accounts?">Move money between accounts once you have two. Add a Bank or Petty Cash account first.</InfoTip></p>
        <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onAddAccount}>Add an account</button>
      </div>
    );
  }
  return (
    <div className="sb-panel" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600"><span>About transfers</span> <InfoTip label="About transfers">A transfer moves money from one account to another. It appears in both accounts’ statements.</InfoTip></p>
        <button type="button" className="sb-btn sb-btn-primary" onClick={() => setOpen(true)}>New transfer</button>
      </div>
      {transfers === null ? (
        <p className="text-sm text-slate-500">Loading transfers…</p>
      ) : transfers.length === 0 ? (
        <p className="text-sm text-slate-500">No transfers yet.</p>
      ) : (
        <div>
          {transfers.map((t) => {
            const when = dateLabel(parseSaved(t.entry_date) ?? t.entry_date, { day: "numeric", month: "short" });
            return (
              <ListRow key={t.id}
                title={`${nameOf(t.from_account_id)} → ${nameOf(t.to_account_id)}`}
                subtitle={[t.description, when].filter(Boolean).join(" · ")}
                amount={money(t.amount)} />
            );
          })}
        </div>
      )}
      {open && <MoneyInForm defaultKind="Transfer" onClose={() => setOpen(false)} onSaved={() => { setOpen(false); setRevision((r) => r + 1); }} />}
    </div>
  );
}
