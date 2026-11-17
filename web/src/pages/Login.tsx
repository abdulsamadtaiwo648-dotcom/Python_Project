import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, auth } from "../api";
import { useSession } from "../session";
import ResetPasswordDialog from "../components/ResetPasswordDialog";

export default function Login() {
  const nav = useNavigate();
  const { user, refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "Sign in | SoloBiz";
  }, []);
  useEffect(() => {
    if (user) nav("/dashboard", { replace: true });
  }, [user, nav]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Please enter both email and password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await auth.login(email.trim(), password);
      await refresh();
      nav("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "An unexpected error occurred. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-shell">
        <aside className="login-brand" aria-label="About SoloBiz">
          <a href="/" className="flex items-center gap-3 text-white no-underline" aria-label="SoloBiz home">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 text-base font-extrabold">S</span>
            <span className="text-lg font-bold">SoloBiz</span>
          </a>
          <div className="login-hero-copy">
            <h2 className="text-5xl font-extrabold leading-[1.05] tracking-tight">Welcome back.</h2>
            <p className="login-hero-sub max-w-md text-lg leading-relaxed text-blue-100">
              Sign in to see today’s sales, stock and expenses in one place.
            </p>
          </div>
          <ul className="grid gap-3 text-base text-white">
            {["Sales, stock and expenses together", "Stock alerts on your phone", "Works offline"].map((t) => (
              <li key={t} className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-blue-300" />
                {t}
              </li>
            ))}
          </ul>
        </aside>

        <main className="login-main">
          <div className="login-card">
            <a href="/" className="login-phone-brand" aria-label="SoloBiz home">
              <span className="login-phone-mark" aria-hidden="true">S</span>
              <span>SoloBiz</span>
            </a>
            <a href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:text-blue-900 no-underline" aria-label="Back to home">
              <span aria-hidden="true">←</span> Back to home
            </a>
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Sign in</h1>
              <p className="mt-2 text-sm text-slate-500">Use the email and password you registered with.</p>
            </div>

            {error && (
              <div role="alert" className="mb-4 px-4 py-3 rounded-lg text-xs font-medium text-center bg-red-50 border border-red-200 text-red-700">
                {error}
              </div>
            )}

            <form onSubmit={submit} className="grid gap-4" noValidate>
              <div className="login-field">
                <label htmlFor="login-email">Email</label>
                <input ref={emailRef} id="login-email" type="email" required placeholder="you@example.com"
                  autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="login-field">
                <label htmlFor="login-password">Password</label>
                <input id="login-password" type="password" required placeholder="••••••••"
                  autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <div className="flex justify-end">
                <button type="button" className="cursor-pointer text-sm font-semibold text-blue-700 hover:underline"
                  onClick={() => setResetOpen(true)}>
                  Forgot password?
                </button>
              </div>
              <button type="submit" className="login-submit" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>

            <p className="text-center text-sm text-slate-500">
              New to SoloBiz?{" "}
              <Link to="/register" className="font-semibold text-blue-700 hover:underline">Create an account</Link>
            </p>
            <p className="text-center text-xs text-slate-400">
              <a href="/privacy" className="hover:underline">Privacy Policy</a>
              <span className="px-1.5">·</span>
              <a href="/data-access" className="hover:underline">Data access</a>
            </p>
          </div>
        </main>
      </div>
      {resetOpen && <ResetPasswordDialog initialEmail={email} onClose={() => setResetOpen(false)} />}
    </div>
  );
}
