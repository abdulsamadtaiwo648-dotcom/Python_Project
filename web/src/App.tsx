import { Navigate, Route, Routes } from "react-router-dom";
import { SessionProvider, useSession } from "./session";
import Login from "./pages/Login";

function Gate({ children }: { children: JSX.Element }) {
  const { ready, user } = useSession();
  if (!ready) return null;
  return user ? children : <Navigate to="/login" replace />;
}

function Placeholder({ name }: { name: string }) {
  return <p style={{ padding: 24 }}>{name}</p>;
}

export default function App() {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<Gate><Placeholder name="Dashboard" /></Gate>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </SessionProvider>
  );
}
