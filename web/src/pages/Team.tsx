import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import Sheet from "../components/Sheet";
import { UpgradeNotice, isUpgradeError } from "../components/Upgrade";
import { useData } from "../data";
import { parseSaved } from "../format";
import { dateLabel } from "../format";
import { ConfirmSheet, ListRow } from "../ui";

interface StaffRow { id: string; name: string; email: string; role: string; role_label: string; pages: string[]; created_at: string }
interface Preset { key: string; label: string; pages: string[]; blurb: string }
interface Page { key: string; label: string }
interface TeamResponse { status: string; staff: StaffRow[]; seats: { used: number; limit: number }; roles: Preset[]; pages: Page[] }

const PASSWORD_OK = (p: string) => p.length >= 8 && /[a-zA-Z]/.test(p) && /\d/.test(p);
const since = (iso: string) => dateLabel(parseSaved(iso));

/** The owner's list of staff, with each person's role, pages and seat count. */
export default function Team() {
  const { subscription } = useData();
  const [team, setTeam] = useState<TeamResponse | null>(null);
  const [error, setError] = useState("");
  const [upgrade, setUpgrade] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<StaffRow | null>(null);

  useEffect(() => { document.title = "Team | SoloBiz"; }, []);
  const load = async () => {
    try {
      setTeam(await api.get<TeamResponse>("/api/staff"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your team.");
    }
  };
  useEffect(() => { void load(); }, []);

  const roleSummary = useMemo(() => team?.roles.filter((r) => r.key !== "custom") ?? [], [team]);

  // Removing someone is destructive, so it asks first with a confirm sheet.
  const [pendingRemove, setPendingRemove] = useState<StaffRow | null>(null);
  const [removing, setRemoving] = useState(false);
  async function remove(row: StaffRow) {
    setRemoving(true);
    try {
      await api.del(`/api/staff/${row.id}`);
      setPendingRemove(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove them.");
    } finally {
      setRemoving(false);
    }
  }

  if (!team) return <section className="page-stack"><p className="text-sm text-slate-500" role="status">{error || "Loading your team…"}</p></section>;
  const full = team.seats.used >= team.seats.limit;

  return (
    <section id="tab-team-content" className="tab-content page-stack" aria-labelledby="team-title">
      <div className="page-head">
        <div className="min-w-0">
          <h2 className="page-title" id="team-title">Team</h2>
          <p className="page-sub">Give each person access to only the pages they need.</p>
        </div>
        <button type="button" className="sb-btn sb-btn-primary" disabled={full} onClick={() => { setUpgrade(false); setError(""); setAdding(true); }}>
          + Add staff
        </button>
      </div>

      {error && <p className="sb-error" role="alert">{error}</p>}

      <div className="sb-panel">
        <p className="text-sm text-slate-600">
          Staff seats used: <strong>{team.seats.used} of {team.seats.limit}</strong>
          {team.seats.limit === 0 && " · Staff accounts are part of the Basic and Pro plans."}
        </p>
        {full && team.seats.limit > 0 && <p className="mt-2 text-xs text-slate-500">You have used all your seats. Remove someone to add another.</p>}
      </div>

      {team.staff.length === 0 ? (
        <div className="sb-panel"><p className="text-sm text-slate-500">No staff yet. Add someone and choose the pages they can use.</p></div>
      ) : (
        <div className="ui-card ui-group">
          {team.staff.map((row) => (
            <ListRow key={row.id}
              title={row.name || row.email}
              subtitle={`${row.email} · ${row.role_label} · added ${since(row.created_at)}`}
              chips={<>{row.pages.map((p) => <span key={p}>{team.pages.find((x) => x.key === p)?.label ?? p}</span>)}</>}
              onClick={() => { setError(""); setEditing(row); }}
              trailing={<button type="button" className="sb-btn sb-btn-small sb-btn-danger-text" onClick={() => setPendingRemove(row)}>Remove</button>} />
          ))}
        </div>
      )}

      {pendingRemove && (
        <ConfirmSheet title="Remove this person?" text={`${pendingRemove.name || pendingRemove.email} will no longer be able to sign in.`}
          confirmLabel="Remove" busy={removing} onConfirm={() => void remove(pendingRemove)} onCancel={() => setPendingRemove(null)} />
      )}

      {upgrade && subscription && <UpgradeNotice title="Add more staff" text="Your plan's staff seats are full. Upgrade to add more people." plan="Pro" />}

      {adding && (
        <StaffForm
          title="Add staff"
          presets={roleSummary}
          pages={team.pages}
          onClose={() => setAdding(false)}
          onSubmit={async (body) => {
            await api.post("/api/staff", body);
            setAdding(false);
            await load();
          }}
          onError={(err) => { setUpgrade(isUpgradeError(err)); setError(err instanceof ApiError ? err.message : "Could not add them."); }}
          showPassword
        />
      )}
      {editing && (
        <StaffForm
          title={`Edit ${editing.name || editing.email}`}
          presets={roleSummary}
          pages={team.pages}
          initial={editing}
          onClose={() => setEditing(null)}
          onSubmit={async (body) => {
            await api.put(`/api/staff/${editing.id}`, body);
            setEditing(null);
            await load();
          }}
          onError={(err) => setError(err instanceof ApiError ? err.message : "Could not save.")}
          showPassword
        />
      )}
    </section>
  );
}

function StaffForm(props: {
  title: string; presets: Preset[]; pages: Page[]; initial?: StaffRow; onClose: () => void;
  onSubmit: (body: Record<string, unknown>) => Promise<void>; onError: (err: unknown) => void; showPassword: boolean;
}) {
  const { initial } = props;
  const [name, setName] = useState(initial?.name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(initial?.role ?? "sales");
  const [pages, setPages] = useState<string[]>(initial?.pages ?? []);
  const [localError, setLocalError] = useState("");
  const [busy, setBusy] = useState(false);

  const presetPages = props.presets.find((r) => r.key === role)?.pages ?? pages;
  const chosen = role === "custom" ? pages : presetPages;

  function toggle(page: string) {
    setPages((cur) => (cur.includes(page) ? cur.filter((p) => p !== page) : [...cur, page]));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setLocalError("");
    if (!initial && (!name.trim() || !email.trim())) return setLocalError("Enter their name and email.");
    if (!initial && !PASSWORD_OK(password)) return setLocalError("Set a password of at least 8 characters with a letter and a number. You give this to them to sign in.");
    if (initial && password && !PASSWORD_OK(password)) return setLocalError("A new password needs at least 8 characters with a letter and a number.");
    if (chosen.length === 0) return setLocalError("Choose at least one page for this role.");
    setBusy(true);
    const body: Record<string, unknown> = { name: name.trim(), role, pages: role === "custom" ? pages : [] };
    if (!initial) { body.email = email.trim(); body.password = password; }
    if (initial && password) body.password = password;
    try {
      await props.onSubmit(body);
    } catch (err) {
      props.onError(err);
      setLocalError("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet title={props.title} onClose={props.onClose}
      description={<p className="sb-sheet-sub">{initial ? "Change their role, pages or password." : "You set the password. Give it to them to sign in."}</p>}>
      <form onSubmit={save} className="sb-sheet-body" noValidate>
        <div className="sb-field">
          <label htmlFor="staff-name">Name</label>
          <input id="staff-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Tunde Bello" />
        </div>
        {!initial && (
          <div className="sb-field">
            <label htmlFor="staff-email">Email (used to sign in)</label>
            <input id="staff-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="staff@example.com" />
          </div>
        )}
        <div className="sb-field">
          <label htmlFor="staff-password">{initial ? "New password (leave blank to keep)" : "Password you set for them"}</label>
          <input id="staff-password" type="text" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters, letters and numbers" />
          <p className="sb-help">They cannot change this themselves. Only you can set a new one.</p>
        </div>
        <fieldset className="sb-fieldset">
          <legend>Role</legend>
          <div className="grid gap-2">
            {props.presets.map((r) => (
              <label key={r.key} className="flex items-start gap-3 rounded-xl border border-slate-200 p-3">
                <input type="radio" name="role" value={r.key} checked={role === r.key} onChange={() => setRole(r.key)} className="mt-1 accent-blue-700" />
                <span><span className="block text-sm font-semibold text-slate-900">{r.label}</span><span className="block text-xs text-slate-500">{r.blurb}</span></span>
              </label>
            ))}
            <label className="flex items-start gap-3 rounded-xl border border-slate-200 p-3">
              <input type="radio" name="role" value="custom" checked={role === "custom"} onChange={() => setRole("custom")} className="mt-1 accent-blue-700" />
              <span><span className="block text-sm font-semibold text-slate-900">Custom</span><span className="block text-xs text-slate-500">Tick the pages they can use.</span></span>
            </label>
          </div>
        </fieldset>
        {role === "custom" && (
          <fieldset className="sb-fieldset">
            <legend>Pages</legend>
            <div className="grid grid-cols-2 gap-2">
              {props.pages.map((p) => (
                <label key={p.key} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
                  <input type="checkbox" checked={pages.includes(p.key)} onChange={() => toggle(p.key)} className="h-4 w-4 accent-blue-700" />
                  {p.label}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
          <strong>They will see:</strong> {chosen.map((p) => props.pages.find((x) => x.key === p)?.label ?? p).join(", ") || "nothing yet"}.
          <br />They cannot see Team, Plans or billing, and cannot change their own password.
        </div>
        {localError && <p className="sb-error" role="alert">{localError}</p>}
        <div className="sb-sheet-foot">
          <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose}>Cancel</button>
          <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{busy ? "Saving…" : initial ? "Save changes" : "Add staff"}</button>
        </div>
      </form>
    </Sheet>
  );
}
