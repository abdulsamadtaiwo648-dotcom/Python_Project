import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { moreIcon } from "./icons-more";

export type NavItem = { to: string; label: string; icon: ReactNode; badge?: number };

/**
 * The phone's bottom bar: up to five items, with More opening a menu of the rest.
 * Hidden on desktop, where the sidebar takes over. Respects the home-bar safe area.
 */
export default function BottomNav({ items, moreItems, activeTab, moreTabs, moreOpen, onToggleMore }: {
  items: NavItem[]; moreItems: NavItem[]; activeTab: string; moreTabs: string[]; moreOpen: boolean; onToggleMore: () => void;
}) {
  return (
    <nav id="mobile-bottom-nav" aria-label="App pages"
      className="fixed bottom-0 left-0 right-0 z-50 lg:hidden flex items-stretch bg-white border-t border-slate-200"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      {items.map((n) => (
        <NavLink key={n.to} to={n.to} style={{ textDecoration: "none" }}
          className={({ isActive }) => `mobile-nav-btn ${isActive ? "text-blue-700" : "text-slate-500"}`}>
          <span className="relative">
            {n.icon}
            {n.badge !== undefined && n.badge > 0 && (
              <span data-low-stock-badge className="absolute -top-1.5 -right-2.5 min-w-[1.1rem] rounded-full bg-rose-600 px-1 py-0.5 text-center text-[10px] font-bold leading-none text-white">{n.badge}</span>
            )}
          </span>
          <span className="mobile-nav-label">{n.label}</span>
        </NavLink>
      ))}
      {moreItems.length > 0 && (
        <button id="mobile-more-btn" type="button" aria-expanded={moreOpen} aria-controls="mobile-more-menu" aria-haspopup="true"
          onClick={onToggleMore}
          className={`mobile-nav-btn ${moreTabs.includes(activeTab) ? "text-blue-700" : "text-slate-500"}`}>
          <span className="relative">{moreIcon}</span>
          <span className="mobile-nav-label">More</span>
        </button>
      )}
      {moreOpen && (
        <div id="mobile-more-menu" className="w-56 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl" role="menu" aria-label="More pages">
          {moreItems.map((n) => (
            <NavLink key={n.to} to={n.to} role="menuitem" style={{ textDecoration: "none" }}
              className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-800">
              {n.icon}
              {n.label}
            </NavLink>
          ))}
        </div>
      )}
    </nav>
  );
}
