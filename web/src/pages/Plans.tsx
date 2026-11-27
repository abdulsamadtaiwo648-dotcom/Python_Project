import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useData } from "../data";
import { money } from "../format";
import type { FeatureKey, PlanInfo } from "../types";
import { dateLabel as formatLongDate } from "../format";
import { ConfirmSheet, ListRow } from "../ui";

const FEATURE_ORDER: FeatureKey[] = ["offline", "reports", "alerts", "branding", "website"];
const dateLabel = (iso: string | null) => formatLongDate(iso);

function limitsFor(p: PlanInfo): string[] {
  return [
    p.max_products === null ? "Unlimited products" : `Up to ${p.max_products} products`,
    p.history_days === null ? "Full sales and expense history" : p.history_days >= 365 ? "12 months of sales and expense history" : `Last ${p.history_days} days of sales and expenses`,
  ];
}

export default function Plans() {
  const { subscription, reload } = useData();
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const result = params.get("payment");

  useEffect(() => { document.title = "Plans | SoloBiz"; }, []);
  useEffect(() => {
    if (!result) return;
    setNotice(
      result === "success" ? "Payment received. Your plan is active." :
      result === "cancelled" ? "Payment cancelled. You were not charged." :
      result === "pending" ? "We are confirming your payment. Your plan will update in a moment." :
      "The payment did not go through. You were not charged for this attempt.");
    void reload();
    setParams({}, { replace: true });
  }, [result, reload, setParams]);

  if (!subscription) return <p className="p-6 text-sm text-slate-500" role="status">Loading plans…</p>;
  const { current, plans, feature_labels: labels } = subscription;

  async function choose(plan: PlanInfo) {
    setBusy(plan.key);
    setError("");
    try {
      const r = await api.post<{ link: string }>("/api/subscription/checkout", { plan: plan.key });
      // Only follow a secure link from the payment provider; never a relative or script URL.
      if (!/^https:\/\//i.test(r.link)) throw new Error("Could not start the payment. Try again.");
      window.location.href = r.link;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the payment. Try again.");
      setBusy(null);
    }
  }

  // Cancelling renewal asks first, with the shared confirm sheet.
  const [confirmCancel, setConfirmCancel] = useState(false);
  async function cancel() {
    setConfirmCancel(false);
    setBusy("cancel");
    try {
      await api.post("/api/subscription/cancel");
      await reload();
      setNotice("Renewal cancelled. Your plan stays until the end of the period.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const summary =
    current.state === "trial" ? `Your free ${subscription.trial_days}-day Pro trial ends on ${dateLabel(current.ends_at)} (${current.days_left} day${current.days_left === 1 ? "" : "s"} left).` :
    current.state === "active" ? `${current.plan_name} is active until ${dateLabel(current.ends_at)}${current.cancel_at_period_end ? ". It will not renew." : "."}` :
    current.state === "grace" ? `Your last renewal was not received. ${current.plan_name} keeps working until ${dateLabel(current.ends_at)}.` :
    current.trial_used ? "Your trial has ended. You are on the Free plan." : "You are on the Free plan.";

  return (
    <section id="tab-plans-content" className="tab-content page-stack" aria-labelledby="plans-title">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="plans-title">Plans</h2>
          <p className="page-sub">Pick what fits your business. Change or cancel any time.</p>
        </div>
      </div>

      {notice && <div className={`plan-banner ${result === "success" ? "plan-banner-trial" : "plan-banner-free"}`} role="status">{notice}</div>}
      {error && <p className="sb-error" role="alert">{error}</p>}

      <div className={`plan-banner ${current.state === "grace" ? "plan-banner-grace" : current.state === "trial" ? "plan-banner-trial" : "plan-banner-free"}`}>
        <span><strong>{current.plan_name}</strong> · {summary}</span>
        {current.state === "active" && !current.cancel_at_period_end && (
          <button type="button" className="underline" disabled={busy === "cancel"} onClick={() => setConfirmCancel(true)}>Cancel renewal</button>
        )}
      </div>

      {!subscription.payments_ready && (
        <p className="plan-banner plan-banner-free" role="note">Online payment is being set up. You can look at the plans now and subscribe as soon as it opens.</p>
      )}

      <div className="plans-grid">
        {plans.map((p) => {
          const isCurrent = current.state !== "trial" ? current.plan === p.key : false;
          const trialingThis = current.state === "trial" && p.key === "pro";
          return (
            <article key={p.key} className={`plan-card ${isCurrent ? "is-current" : ""} ${p.key === "pro" ? "is-popular" : ""}`}>
              <div>
                <p className="plan-name">{p.name}{p.key === "pro" && <span className="plan-chip">Most complete</span>}{isCurrent && <span className="plan-chip">Your plan</span>}{trialingThis && <span className="plan-chip">Trial</span>}</p>
                <p className="plan-tagline">{p.tagline}</p>
              </div>
              <p className="plan-price">{p.price === 0 ? "Free" : money(p.price)}{p.price > 0 && <span> / month</span>}</p>
              <ul className="plan-list">
                {limitsFor(p).map((t) => <li key={t}><span className="yes">✓</span>{t}</li>)}
                {FEATURE_ORDER.map((f) => (
                  <li key={f} className={p.features[f] ? "" : "is-off"}>
                    <span className={p.features[f] ? "yes" : "no"}>{p.features[f] ? "✓" : "–"}</span>{labels[f]}
                  </li>
                ))}
              </ul>
              {p.key === "free" ? (
                <button type="button" className="sb-btn sb-btn-secondary" disabled>{isCurrent ? "Your plan" : "Included"}</button>
              ) : (
                <button type="button" className={`sb-btn ${p.key === "pro" ? "sb-btn-primary" : "sb-btn-secondary"}`}
                  disabled={busy !== null || !subscription.payments_ready} onClick={() => choose(p)}>
                  {busy === p.key ? "Opening payment…" : isCurrent ? `Renew ${p.name}` : current.state === "active" && current.paid_plan && current.paid_plan !== p.key ? `Switch to ${p.name}` : `Choose ${p.name}`}
                </button>
              )}
            </article>
          );
        })}
      </div>

      <p className="page-note">
        Every account starts with a {subscription.trial_days}-day Pro trial. If a renewal is missed, your plan keeps working for {subscription.grace_days} more days, then you move to Free. Nothing is deleted: your records stay, and features that need a paid plan switch off.
      </p>

      {subscription.payments.length > 0 && (
        <div className="sb-panel">
          <h3 className="dash-card-title">Payments</h3>
          <div>
            {subscription.payments.map((p, i) => (
              <ListRow key={i} title={`${p.plan === "pro" ? "Pro" : "Basic"} plan`} subtitle={dateLabel(p.created_at)} amount={money(p.amount)} />
            ))}
          </div>
        </div>
      )}
      {confirmCancel && (
        <ConfirmSheet title="Cancel renewal?" text="Your plan stays until the end of the period you paid for, and then it will not renew."
          confirmLabel="Cancel renewal" onConfirm={() => void cancel()} onCancel={() => setConfirmCancel(false)} />
      )}
    </section>
  );
}
