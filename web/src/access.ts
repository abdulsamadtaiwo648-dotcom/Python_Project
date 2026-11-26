import type { Access } from "./api";

/** Route paths of the app, in the order the sidebar lists them. */
export const PAGE_ROUTES: { path: string; page: string; label: string }[] = [
  { path: "/dashboard", page: "dashboard", label: "Dashboard" },
  { path: "/sales", page: "sales", label: "Sales" },
  { path: "/inventory", page: "inventory", label: "Inventory" },
  { path: "/expenses", page: "expenses", label: "Expenses" },
  { path: "/budget", page: "budget", label: "Budget" },
  { path: "/reports", page: "reports", label: "Reports" },
  { path: "/profile", page: "profile", label: "Profile" },
  { path: "/website", page: "website", label: "Website" },
];

/** Owner-only areas: staff never see these, whatever their pages. */
export const OWNER_ONLY = new Set(["team", "plans", "accounts"]);

export function canUse(access: Access | null, page: string): boolean {
  if (!access) return true;              // still loading: the server decides
  if (access.is_owner) return true;
  if (OWNER_ONLY.has(page)) return false;
  return access.pages.includes(page);
}

/** Where a person lands when they open the app or a page they cannot use. */
export function firstAllowedPath(access: Access | null): string | null {
  if (!access || access.is_owner) return "/dashboard";
  const hit = PAGE_ROUTES.find((r) => access.pages.includes(r.page));
  return hit ? hit.path : null;
}
