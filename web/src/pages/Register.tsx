import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, auth } from "../api";
import AuthShell from "../components/AuthShell";

const PASSWORD_OK = (p: string) => p.length >= 8 && /[a-zA-Z]/.test(p) && /\d/.test(p);

export default function Register() {
  const nav = useNavigate();
  const [step, setStep] = useState<1 | 2>(1);
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", password: "", confirm_password: "" });
  const [privacy, setPrivacy] = useState(false);
  const [show, setShow] = useState(false);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(0);
  const timer = useRef<number>();

  useEffect(() => {
    document.title = "Create account | SoloBiz";
    return () => window.clearInterval(timer.current);
  }, []);

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

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
      setNotice({ text: err instanceof ApiError ? err.message : "Could not reach the server. Please try again.", error: true });
    } finally {
      setBusy(false);
    }
  }

  function requestCode(e: FormEvent) {
    e.preventDefault();
    const email = form.email.trim();
    if (!email || !form.first_name.trim() || !form.last_name.trim() || !form.password || !form.confirm_password) {
      return setNotice({ text: "Complete all required fields.", error: true });
    }
    if (!privacy) return setNotice({ text: "Please review and accept the Privacy Policy to create an account.", error: true });
    if (form.password !== form.confirm_password) return setNotice({ text: "Passwords do not match.", error: true });
    if (!PASSWORD_OK(form.password)) {
      return setNotice({ text: "Password must be at least 8 characters long and contain both letters and numbers.", error: true });
    }
    void run(async () => {
      const r = await auth.registerRequest({
        ...form, email, first_name: form.first_name.trim(), last_name: form.last_name.trim(), privacy_accepted: privacy,
      });
      setNotice({ text: r.message ?? "", error: false });
      setStep(2);
      startTimer();
    });
  }

  const verify = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await auth.registerVerify(form.email.trim(), code.trim());
      nav("/login", { replace: true });
    });
  };
  const resend = () =>
    void run(async () => {
      const r = await auth.registerResend(form.email.trim());
      setNotice({ text: r.message ?? "", error: false });
      startTimer();
    });

  return (
    <AuthShell
      heading="Start in minutes."
      sub="Create your account, verify your email and set up your business."
      points={["Set up in minutes", "Receipts and a business website", "Your data stays on your account"]}
      className="reg-form"
    >
      <div>
        <h1 id="page-title" className="text-3xl font-extrabold tracking-tight text-slate-900">
          {step === 1 ? "Create your account" : "Verify your email"}
        </h1>
        <p id="page-subtitle" className="mt-2 text-sm text-slate-500">
          {step === 1
            ? "Step 1 of 2: your details. We send a code to verify your email."
            : "Enter the 6-digit code sent to your inbox."}
        </p>
      </div>

      {notice && (
        <div role="alert" className={`mb-4 rounded-xl border p-3.5 text-center text-xs font-semibold ${
          notice.error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
          {notice.text}
        </div>
      )}

      {step === 1 ? (
        <form onSubmit={requestCode} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="login-field">
              <label htmlFor="reg-first-name">First name</label>
              <input id="reg-first-name" required autoComplete="given-name" placeholder="First name" value={form.first_name} onChange={set("first_name")} />
            </div>
            <div className="login-field">
              <label htmlFor="reg-last-name">Last name</label>
              <input id="reg-last-name" required autoComplete="family-name" placeholder="Last name" value={form.last_name} onChange={set("last_name")} />
            </div>
          </div>
          <div className="login-field">
            <label htmlFor="reg-email">Email address</label>
            <input id="reg-email" type="email" required placeholder="you@example.com" autoComplete="email" value={form.email} onChange={set("email")} />
          </div>
          <div className="login-field">
            <label htmlFor="reg-password">Password</label>
            <div className="relative">
              <input id="reg-password" type={show ? "text" : "password"} required minLength={8} autoComplete="new-password"
                placeholder="At least 8 characters" className="pr-14" value={form.password} onChange={set("password")} />
              <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-500 hover:text-slate-900">
                {show ? "Hide" : "Show"}
              </button>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">Use at least 8 characters, including a letter and a number.</p>
          </div>
          <div className="login-field">
            <label htmlFor="reg-confirm-password">Confirm password</label>
            <input id="reg-confirm-password" type={show ? "text" : "password"} required minLength={8} autoComplete="new-password"
              placeholder="Enter your password again" value={form.confirm_password} onChange={set("confirm_password")} />
          </div>
          <label htmlFor="privacy-accepted" className="flex items-start gap-2.5 text-xs leading-5 text-slate-600">
            <input type="checkbox" id="privacy-accepted" required checked={privacy} onChange={(e) => setPrivacy(e.target.checked)}
              className="mt-1 h-4 w-4 shrink-0 accent-blue-600" />
            <span>
              I have read and agree to the{" "}
              <a href="/privacy" target="_blank" rel="noopener noreferrer" className="font-semibold text-blue-600 underline underline-offset-2">Privacy Policy</a>.
            </span>
          </label>
          <button type="submit" className="login-submit" disabled={busy}>{busy ? "Sending code…" : "Send verification code"}</button>
        </form>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-xl border border-blue-100 bg-blue-50 p-3.5">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium text-blue-700">Code sent to</p>
              <p className="truncate text-xs font-semibold text-slate-900">{form.email}</p>
            </div>
            <button type="button" className="text-[11px] font-semibold text-blue-600 hover:text-blue-800" onClick={() => { setStep(1); setNotice(null); }}>
              Change
            </button>
          </div>
          <form onSubmit={verify} className="space-y-4">
            <div className="login-field">
              <div className="flex items-center justify-between">
                <label htmlFor="reg-otp">6-digit verification code</label>
                <button type="button" onClick={resend} disabled={wait > 0 || busy}
                  className="text-xs font-semibold text-blue-700 hover:underline disabled:text-slate-400 disabled:no-underline">
                  {wait > 0 ? `Resend code (${wait}s)` : "Resend code"}
                </button>
              </div>
              <input id="reg-otp" inputMode="numeric" maxLength={6} required autoFocus placeholder="123456" value={code}
                onChange={(e) => setCode(e.target.value)} className="text-center tracking-[0.4em] text-xl" />
            </div>
            <button type="submit" className="login-submit" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
          </form>
        </div>
      )}

      <p className="mt-6 text-center text-xs text-slate-500">
        Already have an account? <Link to="/login" className="font-semibold text-blue-600 hover:underline">Sign in</Link>
      </p>
    </AuthShell>
  );
}
