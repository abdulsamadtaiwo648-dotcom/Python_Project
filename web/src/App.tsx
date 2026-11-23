import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { DataProvider } from "./data";
import { canUse, firstAllowedPath } from "./access";
import Budget from "./pages/Budget";
import Dashboard from "./pages/Dashboard";
import Expenses from "./pages/Expenses";
import Inventory from "./pages/Inventory";
import Login from "./pages/Login";
import Plans from "./pages/Plans";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import Reports from "./pages/Reports";
import Sales from "./pages/Sales";
import Team from "./pages/Team";
import Website from "./pages/Website";
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
            <Route path="/budget" element={<Guard page="budget"><Budget /></Guard>} />
            <Route path="/profile" element={<Guard page="profile"><Profile /></Guard>} />
            <Route path="/website" element={<Guard page="website"><Website /></Guard>} />
            <Route path="/plans" element={<Guard page="plans"><Plans /></Guard>} />
            <Route path="/team" element={<Guard page="team"><Team /></Guard>} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </SessionProvider>
  );
}
