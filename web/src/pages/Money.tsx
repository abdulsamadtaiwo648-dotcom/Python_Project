import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { canTransfer } from "../accounts";
import { canUse } from "../access";
import { useData } from "../data";
import { useSession } from "../session";
import Accounts from "./Accounts";
import MoneyIn, { MoneyInForm } from "./MoneyIn";

type Tab = "accounts" | "moneyin" | "transfers";

/** Money: accounts, money in, and transfers between accounts, one page with tabs. */
export default function Money() {
  const { access } = useSession();
  const showAccounts = canUse(access, "accounts");
  const tabs: Tab[] = showAccounts ? ["accounts", "moneyin", "transfers"] : ["moneyin", "transfers"];
  const [params, setParams] = useSearchParams();
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
    </section>
  );
}

function Transfers(props: { onAddAccount: () => void }) {
  const { accounts } = useData();
  const [open, setOpen] = useState(false);
  if (!canTransfer(accounts)) {
    return (
      <div className="sb-panel flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">Move money between accounts once you have two. Add a Bank or Petty Cash account first.</p>
        <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onAddAccount}>Add an account</button>
      </div>
    );
  }
  return (
    <div className="sb-panel flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-slate-600">A transfer moves money from one account to another. It appears in both accounts’ statements.</p>
      <button type="button" className="sb-btn sb-btn-primary" onClick={() => setOpen(true)}>New transfer</button>
      {open && <MoneyInForm defaultKind="Transfer" onClose={() => setOpen(false)} onSaved={() => setOpen(false)} />}
    </div>
  );
}
