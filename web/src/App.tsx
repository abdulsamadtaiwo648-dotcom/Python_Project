import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import Skeleton from "./components/Skeleton";
import Layout from "./components/Layout";
import { DataProvider } from "./data";
import { canUse, firstAllowedPath } from "./access";
// Every page is loaded on demand, so a first visit only downloads the shell and the page it opens.
const Budget = lazy(() => import("./pages/Budget"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Expenses = lazy(() => import("./pages/Expenses"));
const Money = lazy(() => import("./pages/Money"));
const Inventory = lazy(() => import("./pages/Inventory"));
const Login = lazy(() => import("./pages/Login"));
const Plans = lazy(() => import("./pages/Plans"));
const Profile = lazy(() => import("./pages/Profile"));
const Register = lazy(() => import("./pages/Register"));
const Reports = lazy(() => import("./pages/Reports"));
const Sales = lazy(() => import("./pages/Sales"));
const Team = lazy(() => import("./pages/Team"));
const Website = lazy(() => import("./pages/Website"));
import { SessionProvider, useSession } from "./session";

function Protected() {
  const { ready, user } = useSession();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <DataProvider>
      <Outlet />
    </DataProvider>
  );
}

/** Opens a page only for people who may use it; anyone else goes to their first page. */
function Guard({ page, children }: { page: string; children: JSX.Element }) {
  const { access, ready } = useSession();
  if (!ready) return null;
  if (canUse(access, page)) return children;
  const home = firstAllowedPath(access);
  if (home) return <Navigate to={home} replace />;
  return <NoAccess />;
}

function NoAccess() {
  return (
    <section className="page-stack" role="status">
      <div className="page-head"><div className="min-w-0"><h2 className="page-title">No pages yet</h2></div></div>
      <div className="sb-panel">
        <p className="text-sm text-slate-600">Your account does not have any pages yet. Ask the business owner to give you access.</p>
      </div>
    </section>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <Suspense fallback={<Skeleton rows={3} label="Loading page" />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<Protected />}>
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<Guard page="dashboard"><Dashboard /></Guard>} />
            <Route path="/reports" element={<Guard page="reports"><Reports /></Guard>} />
            <Route path="/sales" element={<Guard page="sales"><Sales /></Guard>} />
            <Route path="/inventory" element={<Guard page="inventory"><Inventory /></Guard>} />
            <Route path="/expenses" element={<Guard page="expenses"><Expenses /></Guard>} />
            <Route path="/money" element={<Guard page="sales"><Money /></Guard>} />
            <Route path="/money-in" element={<Navigate to="/money?tab=moneyin" replace />} />
            <Route path="/accounts" element={<Navigate to="/money?tab=accounts" replace />} />
            <Route path="/budget" element={<Guard page="budget"><Budget /></Guard>} />
            <Route path="/profile" element={<Guard page="profile"><Profile /></Guard>} />
            <Route path="/website" element={<Guard page="website"><Website /></Guard>} />
            <Route path="/plans" element={<Guard page="plans"><Plans /></Guard>} />
            <Route path="/team" element={<Guard page="team"><Team /></Guard>} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      </Suspense>
    </SessionProvider>
  );
}
