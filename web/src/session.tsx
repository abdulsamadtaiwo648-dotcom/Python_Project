import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { loadSession, type Access, type SessionUser } from "./api";

interface SessionState {
  ready: boolean;
  user: (SessionUser & { business_owner?: string }) | null;
  access: Access | null;
  refresh: () => Promise<void>;
}

const Ctx = createContext<SessionState>({ ready: false, user: null, access: null, refresh: async () => {} });

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<SessionState, "refresh">>({ ready: false, user: null, access: null });
  const refresh = useCallback(async () => {
    try {
      const info = await loadSession();
      setState({ ready: true, user: info.user, access: info.access });
    } catch {
      // Offline: keep whatever we last knew so the app shell still opens.
      setState((s) => ({ ...s, ready: true }));
    }
  }, []);
  useEffect(() => {
    void refresh();
    const onOut = () => setState({ ready: true, user: null, access: null });
    window.addEventListener("solobiz:signed-out", onOut);
    return () => window.removeEventListener("solobiz:signed-out", onOut);
  }, [refresh]);
  return <Ctx.Provider value={{ ...state, refresh }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
