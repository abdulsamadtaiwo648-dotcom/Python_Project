import { Link } from "react-router-dom";
import { ApiError } from "../api";

/** True when the server answered "your plan does not include this". */
export const isUpgradeError = (e: unknown): e is ApiError =>
  e instanceof ApiError && (e.body as { code?: string } | undefined)?.code === "upgrade_required";

/** A card that explains a locked feature and points to the plans. */
export function UpgradeNotice(props: { title: string; text: string; plan?: string }) {
  return (
    <div className="upgrade-notice" role="note">
      <span className="upgrade-lock" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="upgrade-title">{props.title}</p>
        <p className="upgrade-text">{props.text}</p>
      </div>
      <Link to="/plans" className="sb-btn sb-btn-small sb-btn-primary">See plans{props.plan ? ` · ${props.plan}` : ""}</Link>
    </div>
  );
}

/** Shown in place of a whole page the current plan does not include. */
export function LockedPage(props: { title: string; text: string; plan: string }) {
  return (
    <section className="page-stack">
      <div className="page-head"><div className="min-w-0"><h2 className="page-title">{props.title}</h2></div></div>
      <UpgradeNotice title={`${props.title} is part of ${props.plan}`} text={props.text} plan={props.plan} />
    </section>
  );
}
