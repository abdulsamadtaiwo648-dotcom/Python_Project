import type { ReactNode } from "react";

/** The two-column frame shared by sign-in and register. */
export default function AuthShell(props: {
  heading: string; sub: string; points: string[]; className?: string; children: ReactNode;
}) {
  return (
    <div className="login-page">
      <div className="login-shell">
        <aside className="login-brand" aria-label="About SoloBiz">
          <a href="/" className="flex items-center gap-3 text-white no-underline" aria-label="SoloBiz home">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 text-base font-extrabold">S</span>
            <span className="text-lg font-bold">SoloBiz</span>
          </a>
          <div className="login-hero-copy">
            <h2 className="text-5xl font-extrabold leading-[1.05] tracking-tight">{props.heading}</h2>
            <p className="login-hero-sub max-w-md text-lg leading-relaxed text-blue-100">{props.sub}</p>
          </div>
          <ul className="grid gap-3 text-base text-white">
            {props.points.map((t) => (
              <li key={t} className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-blue-300" />
                {t}
              </li>
            ))}
          </ul>
        </aside>
        <main className="login-main">
          <div className={`login-card ${props.className ?? ""}`}>
            <a href="/" className="login-phone-brand" aria-label="SoloBiz home">
              <span className="login-phone-mark" aria-hidden="true">S</span>
              <span>SoloBiz</span>
            </a>
            <a href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:text-blue-900 no-underline" aria-label="Back to home">
              <span aria-hidden="true">←</span> Back to home
            </a>
            {props.children}
            <p className="text-center text-xs text-slate-400">
              <a href="/privacy" className="hover:underline">Privacy Policy</a>
              <span className="px-1.5">·</span>
              <a href="/data-access" className="hover:underline">Data access</a>
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
