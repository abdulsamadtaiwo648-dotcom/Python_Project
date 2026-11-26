import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { auth } from "../api";
import { useData } from "../data";
import { useSession } from "../session";
import { ICONS } from "../icons";
import { clearDeviceData, signOutWarning } from "../offline";
import { canUse } from "../access";

// Five main pages, then More. Money is one page with tabs (Accounts, Money in, Transfers).
const NAV = [
  { to: "/dashboard", label: "Home", tab: "dashboard" },
  { to: "/sales", label: "Sales", tab: "income" },
  { to: "/expenses", label: "Expenses", tab: "expenses" },
  { to: "/money", label: "Money", tab: "money", page: "sales" },
  { to: "/inventory", label: "Stock", tab: "inventory" },
] as const;

const MOBILE = [
  { to: "/dashboard", label: "Home" },
  { to: "/sales", label: "Sales" },
  { to: "/expenses", label: "Expenses" },
  { to: "/money", label: "Money", page: "sales" },
  { to: "/inventory", label: "Stock" },
] as const;

const MORE_ALL = [
  { to: "/reports", label: "Reports" },
  { to: "/team", label: "Team" },
  { to: "/website", label: "Website" },
  { to: "/profile", label: "Settings" },
  { to: "/plans", label: "Plans" },
  { to: "/budget", label: "Budget" },
] as const;

// `html` must always be a constant icon from ICONS below, never user or server data:
// it is inserted as raw markup.
const Svg = ({ html, className = "w-4 h-4 flex-shrink-0", sw = 2 }: { html: string; className?: string; sw?: number }) => (
  <svg className={className} aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={sw}
    strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: html }} />
);

export function tabFor(pathname: string): string {
  return NAV.find((n) => pathname.startsWith(n.to))?.tab ?? "dashboard";
}

export default function Layout() {
  const { pathname } = useLocation();
  const nav = useNavigate();
  const { refresh, access, user } = useSession();
  const { summary, profile, online, pending, failed, dismissFailed, syncNow, subscription } = useData();
  const plan = subscription?.current;
  const isOwner = !access || access.is_owner;
  const name = user?.first_name || summary?.username || "";
  // A nav item is shown when the person may use its page. Most items are named after their route.
  const pageOf = (n: { to: string; page?: string }) => n.page ?? n.to.slice(1);
  const NAV_SHOWN = NAV.filter((n) => canUse(access, pageOf(n)));
  const MOBILE_SHOWN = MOBILE.filter((n) => canUse(access, pageOf(n)));
  const MORE = MORE_ALL.filter((n) => canUse(access, pageOf(n)));
  const [moreOpen, setMoreOpen] = useState(false);
  const tab = tabFor(pathname);
  const lowCount = summary?.low_stock_items.length ?? 0;
  const businessName = profile?.company_name || "SoloBiz";
  const todayLabel = new Date().toLocaleDateString("en-NG", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  useEffect(() => {
    document.body.dataset.page = tab;
    document.body.classList.add("app-shell", "bg-gray-50", "text-slate-800");
    return () => {
      delete document.body.dataset.page;
      document.body.classList.remove("app-shell", "bg-gray-50", "text-slate-800");
    };
  }, [tab]);
  useEffect(() => setMoreOpen(false), [pathname]);
  useEffect(() => {
    // Closing the tab is safe (the changes stay saved); this only guards against clearing site data by mistake.
    document.title = pending > 0 ? `(${pending}) ${document.title.replace(/^\(\d+\) /, "")}` : document.title.replace(/^\(\d+\) /, "");
  }, [pending, pathname]);

  async function signOut() {
    const userId = user?.id;
    if (pending > 0 && !window.confirm(signOutWarning(pending))) return;
    try {
      await auth.logout();
    } finally {
      if (userId) await clearDeviceData(userId);
      await refresh();
      nav("/login", { replace: true });
    }
  }

  const linkClass = (active: boolean) =>
    `tab-btn ${active ? "bg-blue-700 text-white shadow-sm" : "text-slate-500 hover:text-slate-800 hover:bg-slate-100"}`;

  return (
    <>
      <header className="app-topbar bg-white text-slate-900 sticky top-0 z-40">
        <div className="topbar-inner flex items-center justify-between gap-3">
          {/* Phones: brand on the left. Desktop: the sidebar carries the brand, so this is a welcome. */}
          <div className="flex items-center gap-2.5 lg:hidden">
            <div className="w-8 h-8 rounded-xl overflow-hidden flex-shrink-0 bg-blue-700 flex items-center justify-center shadow-md">
              <img src={profile?.logo_url || "/static/logo.svg"} alt="" className="w-full h-full object-cover rounded-xl" />
            </div>
            <h1 className="font-bold text-base tracking-tight text-slate-900">{businessName}</h1>
          </div>
          <div className="topbar-welcome hidden lg:block min-w-0">
            <p className="truncate text-[15px] font-semibold text-slate-900">Welcome back, {name}</p>
            <p className="truncate text-xs text-slate-500">{todayLabel}</p>
          </div>

          <Link to="/profile" className="topbar-profile hidden lg:flex" aria-label="Open your profile">
            <span className="topbar-avatar" aria-hidden="true">
              {profile?.logo_url ? <img src={profile.logo_url} alt="" /> : (businessName || "S").slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 text-left">
              <span className="block truncate text-sm font-semibold text-slate-900">{name}</span>
              <span className="block truncate text-xs text-slate-500">{businessName}</span>
            </span>
          </Link>
          <button type="button" onClick={signOut} aria-label="Sign out"
            className="lg:hidden text-xs font-semibold text-slate-600 hover:text-slate-900 transition bg-white border border-slate-200 hover:bg-slate-50 min-h-[40px] px-3 rounded-xl inline-flex items-center gap-1.5">
            <Svg html={ICONS.signout} className="w-3.5 h-3.5" />
            <span className="sb-logout-label">Sign out</span>
          </button>
        </div>
      </header>

      <main className="desktop-dashboard-shell w-full">
        <aside id="dashboard-navigation" className="desktop-sidebar" aria-label="Main navigation">
          <div className="side-brand">
            <img src="/static/logo.svg" alt="" width={32} height={32} />
            <div className="min-w-0"><p className="side-brand-name">SoloBiz</p></div>
          </div>
          <p className="nav-group">Main</p>
          {NAV_SHOWN.map((n) => (
            <NavLink key={n.to} to={n.to} id={`btn-tab-${n.tab}`} data-dashboard-tab={n.tab}
              className={({ isActive }) => linkClass(isActive)}>
              <Svg html={ICONS[n.to]} />
              <span>{n.label}</span>
              {n.tab === "inventory" && lowCount > 0 && (
                <span data-low-stock-badge className="ml-auto min-w-[1.25rem] rounded-full bg-rose-600 px-1.5 py-0.5 text-center text-[10px] font-bold leading-none text-white"
                  aria-label={`${lowCount} products low on stock`}>{lowCount}</span>
              )}
            </NavLink>
          ))}
          {MORE.length > 0 && <p className="nav-group">More</p>}
          {MORE.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => linkClass(isActive)}>
              <Svg html={ICONS["m" + n.to]} />
              <span>{n.label}</span>
            </NavLink>
          ))}
          <div className="side-business">
            <span className="side-business-mark" aria-hidden="true">{(name || "S").slice(0, 1).toUpperCase()}</span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">{name}</p>
              <p className="truncate text-xs text-slate-500">{isOwner ? (plan ? (plan.state === "trial" ? "Pro trial" : `${plan.plan_name} plan`) : " ") : (access?.role_label ? `${access.role_label} staff` : "Staff")}</p>
            </div>
          </div>
          <div className="side-foot">
            <button type="button" className="side-signout" onClick={signOut}>
              <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                dangerouslySetInnerHTML={{ __html: ICONS.signout }} />
              Sign out
            </button>
          </div>
        </aside>

        <div className="desktop-content">
          {isOwner && plan && pathname !== "/plans" && plan.state === "trial" && (
            <div className="plan-banner plan-banner-trial" role="status">
              <span>Pro trial: {plan.days_left} day{plan.days_left === 1 ? "" : "s"} left. After that you move to the Free plan.</span>
              <Link to="/plans">See plans</Link>
            </div>
          )}
          {isOwner && plan && pathname !== "/plans" && plan.state === "grace" && (
            <div className="plan-banner plan-banner-grace" role="alert">
              <span>Your {plan.plan_name} renewal was not received. Everything keeps working until {plan.ends_at ? new Date(plan.ends_at).toLocaleDateString("en-NG", { day: "numeric", month: "long" }) : "soon"}.</span>
              <Link to="/plans">Renew now</Link>
            </div>
          )}
          {isOwner && plan && pathname === "/dashboard" && plan.state === "free" && (
            <div className="plan-banner plan-banner-free" role="note">
              <span>{plan.trial_used ? "Your trial has ended. You are on the Free plan." : "You are on the Free plan."} Reports, website, alerts and offline recording need Basic or Pro.</span>
              <Link to="/plans">See plans</Link>
            </div>
          )}
          {!online && (
            <div role="status" className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900">
              <span>
                You are offline. Sales and expenses you record are saved on this device and sent when you reconnect.
                {pending > 0 ? ` ${pending} waiting.` : ""}
              </span>
            </div>
          )}
          {online && pending > 0 && (
            <div role="status" className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs font-semibold text-blue-900">
              <span>{pending} change{pending === 1 ? "" : "s"} saved on this device, syncing…</span>
              <button type="button" className="rounded-lg bg-blue-700 px-3 py-1.5 text-[10px] font-black uppercase tracking-wide text-white" onClick={() => void syncNow()}>Retry sync</button>
            </div>
          )}
          {failed.length > 0 && (
            <div role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-900">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p>{failed.length} change{failed.length === 1 ? "" : "s"} made offline could not be saved:</p>
                  <ul className="mt-1 list-disc pl-4 font-medium">{failed.map((f) => <li key={f.id}>{f.message}</li>)}</ul>
                </div>
                <button type="button" className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-wide" onClick={dismissFailed}>Dismiss</button>
              </div>
            </div>
          )}
          <Outlet />
        </div>
      </main>

      <nav id="mobile-bottom-nav" aria-label="App pages"
        className="fixed bottom-0 left-0 right-0 z-50 lg:hidden flex items-stretch bg-white border-t border-slate-200"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        {MOBILE_SHOWN.map((n) => (
          <NavLink key={n.to} to={n.to} style={{ textDecoration: "none" }}
            className={({ isActive }) => `mobile-nav-btn ${isActive ? "text-blue-700" : "text-slate-500"}`}>
            <span className="relative">
              <Svg html={ICONS["m" + n.to]} className="w-6 h-6" sw={1.9} />
              {n.to === "/inventory" && lowCount > 0 && (
                <span data-low-stock-badge className="absolute -top-1.5 -right-2.5 min-w-[1.1rem] rounded-full bg-rose-600 px-1 py-0.5 text-center text-[10px] font-bold leading-none text-white">{lowCount}</span>
              )}
            </span>
            <span className="mobile-nav-label">{n.label}</span>
          </NavLink>
        ))}
        {MORE.length > 0 && (
        <button id="mobile-more-btn" type="button" aria-expanded={moreOpen} aria-controls="mobile-more-menu" aria-haspopup="true"
          onClick={() => setMoreOpen((o) => !o)}
          className={`mobile-nav-btn ${["reports", "budget", "profile", "plans", "team", "website"].includes(tab) ? "text-blue-700" : "text-slate-500"}`}>
          <span className="relative"><Svg html={ICONS.more} className="w-6 h-6" sw={1.9} /></span>
          <span className="mobile-nav-label">More</span>
        </button>
        )}
        {moreOpen && (
          <div id="mobile-more-menu" className="w-56 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl" role="menu" aria-label="More pages">
            {MORE.map((n) => (
              <NavLink key={n.to} to={n.to} role="menuitem" style={{ textDecoration: "none" }}
                className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-800">
                <Svg html={ICONS["m" + n.to]} className="w-5 h-5" />
                {n.label}
              </NavLink>
            ))}
          </div>
        )}
      </nav>
    </>
  );
}
