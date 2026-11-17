import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, auth } from "../api";
import Sheet from "../components/Sheet";
import { useData } from "../data";
import { useSession } from "../session";
import type { BusinessProfile } from "../types";

const REASONS: [string, string][] = [
  ["business_rebrand", "Business rebrand"], ["contact_update", "Contact information update"],
  ["business_relocation", "Business location change"], ["business_details", "Correct business details"], ["other", "Other"],
];

interface SaveResult { status: string; message?: string }

export default function Profile() {
  const nav = useNavigate();
  const { refresh } = useSession();
  const { profile, summary, reload, pending } = useData();
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({ company_name: "", business_phone: "", whatsapp_number: "", instagram_handle: "", business_address: "", store_policy: "", reason: "", note: "" });
  const [logo, setLogo] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [pinOpen, setPinOpen] = useState(false);
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState("");
  const [pinMessage, setPinMessage] = useState("");

  useEffect(() => { document.title = "Profile | SoloBiz"; }, []);

  const exists = Boolean(profile?.company_name);
  const p: BusinessProfile | null = profile;
  const brand = p?.brand_color || "#1d4ed8";

  function startEdit() {
    setForm({
      company_name: p?.company_name ?? "", business_phone: p?.business_phone ?? "", whatsapp_number: p?.whatsapp_number ?? "",
      instagram_handle: p?.instagram_handle ?? "", business_address: p?.business_address ?? "", store_policy: p?.store_policy ?? "",
      reason: "", note: "",
    });
    setLogo(null);
    setError("");
    setNotice("");
    setEditing(true);
  }

  async function requestPin(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.company_name.trim() || !form.business_phone.trim() || !form.business_address.trim()) {
      return setError("Please complete the required business profile fields: company / brand name, business phone, business address.");
    }
    if (exists && !form.reason) return setError("Select a reason for changing your business profile.");
    if (exists && form.reason === "other" && !form.note.trim()) return setError("Add a short explanation for the reason you selected.");
    setBusy(true);
    try {
      const r = await api.post<SaveResult>("/api/business_profile/request-otp");
      setPinMessage(r.message ?? "We sent a verification code to your email.");
      setPin("");
      setPinError("");
      setPinOpen(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the verification code.");
    } finally {
      setBusy(false);
    }
  }

  async function submitPin(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setPinError("");
    const body = new FormData();
    body.set("company_name", form.company_name.trim());
    body.set("business_phone", form.business_phone.trim());
    body.set("business_address", form.business_address.trim());
    body.set("whatsapp_number", form.whatsapp_number.trim());
    body.set("instagram_handle", form.instagram_handle.trim());
    body.set("store_policy", form.store_policy.trim());
    body.set("brand_color", brand);
    body.set("profile_change_reason", form.reason);
    body.set("profile_change_note", form.note.trim());
    body.set("otp", pin.trim());
    if (logo) body.set("logo", logo);
    try {
      await api.post<SaveResult>("/api/business_profile", body);
      await reload();
      setPinOpen(false);
      setEditing(false);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 4000);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not save your profile.";
      if (err instanceof ApiError && err.status === 403) {
        setPinOpen(false);
        setNotice(msg);
      } else setPinError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    if (pending > 0 && !window.confirm(`${pending} change${pending === 1 ? " is" : "s are"} saved on this device but not sent yet. They stay on this device and are sent the next time you sign in with internet. Sign out now?`)) return;
    try { await auth.logout(); } finally { await refresh(); nav("/login", { replace: true }); }
  }

  const storeUrl = `${window.location.origin}/store/${p?.store_slug || ""}`;
  async function copyLink() {
    try { await navigator.clipboard.writeText(storeUrl); setNotice("Shop link copied."); } catch { setNotice(storeUrl); }
  }
  async function share() {
    const data = { title: p?.company_name || "My business", text: `${p?.company_name} — ${p?.business_phone}`, url: storeUrl };
    if (navigator.share) { try { await navigator.share(data); } catch { /* cancelled */ } } else await copyLink();
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <section id="tab-profile-content" className="tab-content page-stack" aria-labelledby="profile-title">
      <div className="page-head">
        <div>
          <h2 className="page-title" id="profile-title">Profile</h2>
          <p className="page-sub">Your business details and how customers find you.</p>
        </div>
        <button type="button" id="btn-profile-save-top" className="sb-btn sb-btn-primary" onClick={() => (editing ? document.getElementById("profile-form")?.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true })) : startEdit())}>
          {editing ? "Save changes" : exists ? "Edit details" : "Add details"}
        </button>
      </div>

      <div id="profile-account" className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-gradient-to-br from-blue-700 to-blue-900 p-6 text-white shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-200">Current plan</p>
          <p className="mt-2 text-2xl font-extrabold">Early access</p>
          <p className="mt-2 text-sm text-blue-100">Your records, sales and business page are all included while SoloBiz is in early access.</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Account</p>
          <p className="mt-2 text-base font-semibold text-slate-900">{summary?.username}</p>
          <p className="mt-1 text-sm text-slate-500">Signed in on this device.</p>
          <button type="button" onClick={signOut} className="mt-4 inline-flex min-h-[44px] items-center justify-center rounded-xl border border-slate-200 px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50">Sign out</button>
        </div>
      </div>

      <div className="sb-panel profile-panel">
        {saved && <div className="sb-success">Business Profile saved successfully!</div>}
        {notice && <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">{notice}</div>}

        {!editing ? (
          <div className="space-y-4">
            <div id="digital-business-card" className="biz-card-v2 relative flex flex-col justify-between space-y-4 overflow-hidden">
              <div className="absolute left-0 right-0 top-0 h-2" style={{ backgroundColor: brand }} />
              <div className="flex items-center gap-3.5 pt-1">
                <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-blue-100 text-xl font-black text-white shadow-md" style={{ backgroundColor: brand }}>
                  {p?.logo_url ? <img src={p.logo_url} alt="Logo" className="h-full w-full object-cover" /> : <span>{(p?.company_name || "B")[0].toUpperCase()}</span>}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="flex items-center gap-1.5 truncate text-lg font-extrabold tracking-tight text-slate-900 sm:text-xl">{p?.company_name || "Your Business"}</h2>
                  <p className="mt-0.5 flex items-center gap-1 text-[11px] font-semibold tracking-wide text-slate-500">
                    <span className={`h-1.5 w-1.5 rounded-full ${exists ? "bg-emerald-500" : "bg-amber-500"}`} />
                    {exists ? "Ready for receipts" : "Add your details to send receipts"}
                  </p>
                </div>
              </div>
              <div className="space-y-2 border-t border-slate-100 pt-1 text-xs">
                <div className="flex items-center gap-2 font-medium text-slate-700"><span>{p?.business_phone || "Not set"}</span></div>
                <div className="flex items-center gap-2 font-medium text-slate-700"><span className="truncate">{p?.business_address || "Not set"}</span></div>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {p?.whatsapp_number && <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-700">WhatsApp {p.whatsapp_number}</span>}
                  {p?.instagram_handle && <span className="inline-flex items-center gap-1 rounded-full border border-pink-200 bg-pink-50 px-2.5 py-1 text-[10px] font-bold text-pink-700">{p.instagram_handle.startsWith("@") ? p.instagram_handle : `@${p.instagram_handle}`}</span>}
                </div>
              </div>
              {p?.store_policy && (
                <div className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-slate-50 p-3 text-[11px] font-medium italic text-slate-600"><span>"{p.store_policy}"</span></div>
              )}
              <div className="shop-link flex items-center justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="shop-link-label">Your shop link</p>
                  <p className="shop-link-url truncate">solobiz.dev/store/{p?.store_slug || "your-store"}</p>
                </div>
                <div className="flex flex-shrink-0 items-center gap-1.5">
                  <button type="button" onClick={copyLink} className="sb-btn sb-btn-small sb-btn-primary">Copy</button>
                  {p?.store_slug && <a href={`/store/${p.store_slug}`} target="_blank" rel="noopener" className="sb-btn sb-btn-small sb-btn-secondary">Visit</a>}
                </div>
              </div>
              <a href="/website" className="website-promo">
                <span><strong>Get a full website</strong><br />Show your products or services at your own address.</span>
                <svg className="h-5 w-5" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="m9 6 6 6-6 6" /></svg>
              </a>
            </div>
            <div className="profile-actions">
              <button type="button" onClick={share} className="sb-btn sb-btn-primary flex-1"><span>Share</span></button>
              <button type="button" onClick={() => window.print()} className="sb-btn sb-btn-secondary flex-1"><span>Download</span></button>
              <button type="button" id="btn-edit-profile" onClick={startEdit} className="sb-btn sb-btn-secondary flex-1"><span>Edit details</span></button>
            </div>
          </div>
        ) : (
          <div>
            <h3 className="profile-panel-title">Business details</h3>
            <form id="profile-form" className="profile-form" onSubmit={requestPin} noValidate>
              {error && <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700" role="alert">{error}</p>}
              {exists && (
                <>
                  <div className="sb-field">
                    <label htmlFor="profile-change-reason">Why are you changing your details?</label>
                    <select id="profile-change-reason" required value={form.reason} onChange={set("reason")}>
                      <option value="">Choose a reason</option>
                      {REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </div>
                  {form.reason === "other" && (
                    <div className="sb-field">
                      <label htmlFor="profile-change-note">Short reason</label>
                      <input id="profile-change-note" maxLength={100} placeholder="Add a short explanation" value={form.note} onChange={set("note")} />
                    </div>
                  )}
                </>
              )}
              <div className="sb-field">
                <label htmlFor="profile-company-name">Business name</label>
                <input id="profile-company-name" placeholder="e.g. Aisha Wears" required value={form.company_name} onChange={set("company_name")} />
              </div>
              <div className="sb-field-row sb-field-row-stack">
                <div className="sb-field">
                  <label htmlFor="profile-business-phone">Phone number</label>
                  <input id="profile-business-phone" type="tel" placeholder="+2348012345678" required value={form.business_phone} onChange={set("business_phone")} />
                </div>
                <div className="sb-field">
                  <label htmlFor="profile-whatsapp-number">WhatsApp number <span className="sb-optional">(optional)</span></label>
                  <input id="profile-whatsapp-number" type="tel" placeholder="+2348012345678" value={form.whatsapp_number} onChange={set("whatsapp_number")} />
                </div>
              </div>
              <div className="sb-field-row sb-field-row-stack">
                <div className="sb-field">
                  <label htmlFor="profile-instagram-handle">Instagram <span className="sb-optional">(optional)</span></label>
                  <input id="profile-instagram-handle" placeholder="@aisha_wears" value={form.instagram_handle} onChange={set("instagram_handle")} />
                </div>
                <div className="sb-field">
                  <label htmlFor="profile-business-address">Address</label>
                  <input id="profile-business-address" placeholder="12 Market St, Lagos" required value={form.business_address} onChange={set("business_address")} />
                </div>
              </div>
              <div className="sb-field">
                <label htmlFor="profile-store-policy">Note on receipts and shop page <span className="sb-optional">(optional)</span></label>
                <textarea id="profile-store-policy" rows={2} placeholder="e.g. No refunds after 24 hours. Thanks for choosing us!" value={form.store_policy} onChange={set("store_policy")} />
              </div>
              <div className="sb-field">
                <label htmlFor="profile-logo-file">Logo <span className="sb-optional">(optional, up to 2 MB)</span></label>
                <input id="profile-logo-file" type="file" className="sb-file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    if (f && f.size > 2 * 1024 * 1024) { window.alert("Image is too large. Max size is 2MB."); e.target.value = ""; setLogo(null); } else setLogo(f);
                  }} />
              </div>
              <div className="profile-actions">
                <button type="button" className="sb-btn sb-btn-secondary flex-1" onClick={() => setEditing(false)}>Cancel</button>
                <button type="submit" className="sb-btn sb-btn-primary flex-1" disabled={busy}>{busy ? "Sending code…" : "Save details"}</button>
              </div>
            </form>
          </div>
        )}
      </div>

      <div className="sb-panel receipt-preview" aria-label="Receipt preview">
        <p className="receipt-preview-label">How your receipt header looks</p>
        <div className="receipt-preview-paper">
          <h4>{(editing ? form.company_name : p?.company_name) || "Your business name"}</h4>
          <p>{(editing ? form.business_phone : p?.business_phone) || "+234 000 000 0000"}</p>
          <p>{(editing ? form.business_address : p?.business_address) || "Business address"}</p>
          <div className="receipt-preview-row"><span>Sample item</span><span>Paid</span></div>
          <p className="receipt-preview-thanks">Thank you for your business!</p>
        </div>
      </div>

      {pinOpen && (
        <Sheet title="Confirm it's you" compact onClose={() => setPinOpen(false)}
          description={<p className="sb-sheet-sub">{pinMessage}</p>}>
          <form onSubmit={submitPin} className="sb-sheet-body">
            <div className="sb-field">
              <label htmlFor="profile-otp">6-digit verification code</label>
              <input id="profile-otp" inputMode="numeric" maxLength={6} required autoFocus placeholder="123456" value={pin} onChange={(e) => setPin(e.target.value)} />
            </div>
            {pinError && <p className="sb-error" role="alert">{pinError}</p>}
            <div className="sb-sheet-foot">
              <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setPinOpen(false)}>Cancel</button>
              <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{busy ? "Saving…" : "Save details"}</button>
            </div>
          </form>
        </Sheet>
      )}
    </section>
  );
}
