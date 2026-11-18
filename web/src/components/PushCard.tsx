import { useEffect, useState } from "react";
import { api } from "../api";
import { useData } from "../data";
import { UpgradeNotice } from "./Upgrade";
import { disablePush, enablePush, pushStatus, type PushState } from "../push";

export default function PushCard() {
  const { can } = useData();
  const [state, setState] = useState<PushState>("loading");
  const [key, setKey] = useState("");
  const [message, setMessage] = useState("Get a notification on this device when a product runs low or sells out, even when SoloBiz is closed.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void pushStatus().then((s) => {
      setState(s.state);
      if (s.key) setKey(s.key);
      if (s.message) setMessage(s.message);
    });
  }, []);

  if (state === "loading" || state === "hidden") return null;
  if (!can("alerts")) {
    return <UpgradeNotice title="Stock alert notifications" text="Get a notification on your phone when a product runs low. Alerts come with the Basic and Pro plans." plan="Basic" />;
  }

  async function toggle() {
    setBusy(true);
    try {
      if (state === "on") {
        await disablePush();
        setState("off");
        setMessage("Notifications are off for this device.");
      } else {
        await enablePush(key);
        setState("on");
        setMessage("Notifications are on for this device.");
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not change notifications.");
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    try {
      await api.post("/api/push/test");
      setMessage("Test notification sent.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not send the test.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="push-settings" className="sb-panel flex flex-wrap items-center gap-3" data-state={state}>
      <svg className="w-5 h-5 flex-shrink-0 text-blue-700" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      <div className="flex-1 min-w-[12rem]">
        <p className="text-sm font-bold text-slate-900">Stock alert notifications</p>
        <p className="text-xs text-slate-500 mt-0.5" aria-live="polite">{message}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {state === "on" && (
          <button type="button" onClick={test} disabled={busy} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50">Send test</button>
        )}
        {state !== "unsupported" && state !== "blocked" && (
          <button type="button" onClick={toggle} disabled={busy}
            className={state === "on"
              ? "rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              : "rounded-lg bg-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-blue-800 disabled:opacity-60"}>
            {state === "on" ? "Turn off" : "Turn on"}
          </button>
        )}
      </div>
    </div>
  );
}
