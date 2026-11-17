import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { auth } from "../api";
import { useData } from "../data";
import { useSession } from "../session";
import { ICONS } from "../icons";

const NAV = [
  { to: "/dashboard", label: "Dashboard", tab: "dashboard" },
  { to: "/sales", label: "Sales", tab: "income" },
  { to: "/inventory", label: "Inventory", tab: "inventory" },
  { to: "/expenses", label: "Expenses", tab: "expenses" },
  { to: "/budget", label: "Budget", tab: "budget" },
  { to: "/reports", label: "Reports", tab: "reports" },
  { to: "/profile", label: "Profile", tab: "profile" },
] as const;

const MOBILE = [
  { to: "/dashboard", label: "Home" },
  { to: "/sales", label: "Sales" },
  { to: "/inventory", label: "Inventory" },
  { to: "/expenses", label: "Expenses" },
] as const;

const MORE = [
  { to: "/reports", label: "Reports" },
  { to: "/budget", label: "Budget" },
  { to: "/profile", label: "Profile" },
  { to: "/website", label: "Website" },
] as const;

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
  const { refresh } = useSession();
  const { summary, profile } = useData();
  const [moreOpen, setMoreOpen] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true), down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => { window.removeEventListener("online", up); window.removeEventListener("offline", down); };
  }, []);
  const tab = tabFor(pathname);
  const lowCount = summary?.low_stock_items.length ?? 0;
  const businessName = profile?.company_name || "SoloBiz";

  useEffect(() => {
    document.body.dataset.page = tab;
    document.body.classList.add("app-shell", "bg-gray-50", "text-slate-800");
    return () => {
      delete document.body.dataset.page;
      document.body.classList.remove("app-shell", "bg-gray-50", "text-slate-800");
    };
  }, [tab]);
  useEffect(() => setMoreOpen(false), [pathname]);

  async function signOut() {
    try {
      await auth.logout();
    } finally {
      await refresh();
      nav("/login", { replace: true });
    }
  }

  const linkClass = (active: boolean) =>
    `tab-btn ${active ? "bg-blue-700 text-white shadow-sm" : "text-slate-500 hover:text-slate-800 hover:bg-slate-100"}`;

  return (
    <>
      <header className="bg-white text-slate-900 p-3.5 sm:p-4 shadow-none sticky top-0 z-40">
        <div className="max-w-screen-2xl mx-auto flex justify-between items-center px-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl overflow-hidden flex-shrink-0 bg-blue-700 flex items-center justify-center shadow-md">
              <img src={profile?.logo_url || "/static/logo.svg"} alt="" className="w-full h-full object-cover rounded-xl" />
            </div>
            <h1 className="font-bold text-base sm:text-lg tracking-tight text-slate-900">{businessName}</h1>
          </div>
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
          {NAV.map((n) => (
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
          <NavLink to="/website" className={({ isActive }) => linkClass(isActive)}>
            <Svg html={ICONS["/website"]} />
            <span>Website</span>
          </NavLink>
          <div className="side-business">
            <span className="side-business-mark" aria-hidden="true">{(summary?.username ?? "S").slice(0, 1).toUpperCase()}</span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">{summary?.username ?? ""}</p>
              <p className="truncate text-xs text-slate-500">Early access</p>
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
          {!online && (
            <div role="status" className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900">
              <span>You are offline. You can look at your last saved records; recording sales and changes needs a connection.</span>
            </div>
          )}
          <Outlet />
        </div>
      </main>

      <nav id="mobile-bottom-nav" aria-label="App pages"
        className="fixed bottom-0 left-0 right-0 z-50 lg:hidden flex items-stretch bg-white border-t border-slate-200"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        {MOBILE.map((n) => (
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
        <button id="mobile-more-btn" type="button" aria-expanded={moreOpen} aria-controls="mobile-more-menu" aria-haspopup="true"
          onClick={() => setMoreOpen((o) => !o)}
          className={`mobile-nav-btn ${["reports", "budget", "profile"].includes(tab) ? "text-blue-700" : "text-slate-500"}`}>
          <span className="relative"><Svg html={ICONS.more} className="w-6 h-6" sw={1.9} /></span>
          <span className="mobile-nav-label">More</span>
        </button>
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
