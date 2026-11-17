import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, auth } from "../api";
import { useSession } from "../session";

type Notice = { text: string; error: boolean } | null;

export default function ResetPasswordDialog({ initialEmail, onClose }: { initialEmail: string; onClose: () => void }) {
  const nav = useNavigate();
  const { refresh } = useSession();
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(0);
  const timer = useRef<number>();

  useEffect(() => () => window.clearInterval(timer.current), []);

  function startTimer() {
    window.clearInterval(timer.current);
    setWait(30);
    timer.current = window.setInterval(() => setWait((w) => (w <= 1 ? (window.clearInterval(timer.current), 0) : w - 1)), 1000);
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      setNotice({ text: err instanceof ApiError ? err.message : "Error connecting to server.", error: true });
    } finally {
      setBusy(false);
    }
  }

  const request = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const r = await auth.forgotRequest(email.trim());
      setNotice({ text: r.message ?? "", error: false });
      setStep(2);
      startTimer();
    });
  };
  const resend = () =>
    void run(async () => {
      const r = await auth.forgotResend(email.trim());
      setNotice({ text: r.message ?? "", error: false });
      startTimer();
    });
  const confirm = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await auth.forgotReset(email.trim(), code.trim(), password);
      setNotice({ text: "Password updated successfully! Logging you in…", error: false });
      await refresh();
      nav("/dashboard", { replace: true });
    });
  };

  return (
    <div className="reset-overlay" role="dialog" aria-modal="true" aria-labelledby="reset-title">
      <div className="reset-card">
        <button type="button" className="reset-close" aria-label="Close" onClick={onClose}>×</button>
        <h2 id="reset-title" className="text-lg font-bold text-slate-900">Reset password</h2>
        <p className="mb-4 mt-1 text-sm text-slate-500">
          {step === 1 ? "Enter your email to receive a verification code." : "Enter the 6-digit code and choose a new password."}
        </p>
        {notice && (
          <div role="status" className={`mb-4 rounded-lg border px-3 py-2 text-xs font-semibold ${
            notice.error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
            {notice.text}
          </div>
        )}
        {step === 1 ? (
          <form onSubmit={request} className="grid gap-4">
            <div className="login-field">
              <label htmlFor="reset-email">Email address</label>
              <input id="reset-email" type="email" required placeholder="name@example.com" value={email}
                onChange={(e) => setEmail(e.target.value)} />
            </div>
            <button type="submit" className="login-submit" disabled={busy}>{busy ? "Sending code…" : "Send verification code"}</button>
          </form>
        ) : (
          <form onSubmit={confirm} className="grid gap-4">
            <div className="login-field">
              <div className="flex items-center justify-between">
                <label htmlFor="reset-code">6-digit verification code</label>
                <button type="button" onClick={resend} disabled={wait > 0 || busy}
                  className="text-xs font-semibold text-blue-700 hover:underline disabled:text-slate-400 disabled:no-underline">
                  {wait > 0 ? `Resend code (${wait}s)` : "Resend code"}
                </button>
              </div>
              <input id="reset-code" inputMode="numeric" maxLength={6} required placeholder="123456" value={code}
                onChange={(e) => setCode(e.target.value)} className="text-center tracking-widest" />
            </div>
            <div className="login-field">
              <label htmlFor="reset-password">New password</label>
              <input id="reset-password" type="password" required minLength={8} placeholder="At least 8 characters, letters and numbers"
                autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <button type="submit" className="login-submit" disabled={busy}>{busy ? "Updating password…" : "Update password"}</button>
          </form>
        )}
      </div>
    </div>
  );
}
