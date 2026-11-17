import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { money } from "../format";
import { shrinkImage } from "../shrinkImage";
import "../styles/website-builder.css";

interface Service { name: string; description: string; price: string | number | null; image_url: string }
interface Action { type: "whatsapp" | "call" | "link"; label: string; value: string }
interface Content {
  layout: "product" | "service"; display_name: string; tagline: string; about: string; brand_color: string;
  logo_url: string; cover_url: string; phone: string; whatsapp: string; email: string; instagram: string;
  address: string; hours: string; action: Action; services: Service[]; gallery: string[];
}
interface SiteProduct { id: number; name: string; price: number; image_url: string; show_on_website: boolean; sold_out: boolean }
interface Site {
  exists: boolean; content: Content; slug: string; address: string; url: string; is_published: boolean;
  has_unpublished_changes: boolean; publish_problems: string[]; products: SiteProduct[]; profile_logo: string; store_url: string;
}
interface SiteResponse { status: string; message?: string; errors?: Record<string, string>; website: Site; problems?: string[] }

const SWATCHES = ["#1d4ed8", "#0F766E", "#BE185D", "#B45309", "#15803D", "#7C3AED", "#0F172A"];
const ACTION_HINTS = {
  whatsapp: { label: "WhatsApp number", placeholder: "+2348012345678", text: "Chat on WhatsApp" },
  call: { label: "Phone number", placeholder: "+2348012345678", text: "Call us" },
  link: { label: "Link", placeholder: "https://…", text: "Request a quote" },
} as const;

type Tone = "" | "ok" | "error";

export default function Website() {
  const [site, setSite] = useState<Site | null>(null);
  const [content, setContent] = useState<Content | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; tone: Tone }>({ text: "", tone: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problems, setProblems] = useState<{ title: string; items: string[] } | null>(null);
  const [preview, setPreview] = useState(false);
  const [copied, setCopied] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const pickResolve = useRef<((url: string | null) => void) | null>(null);

  useEffect(() => {
    document.title = "Website — SoloBiz";
    document.body.classList.add("app-shell");
    api.get<SiteResponse>("/api/website")
      .then((r) => {
        setSite(r.website);
        setContent(r.website.content);
        if (!r.website.exists) setNote({ text: "We filled in what SoloBiz already knows. Check it, then preview and publish.", tone: "" });
      })
      .catch(() => setNote({ text: "Could not load your website settings. Reload the page to try again.", tone: "error" }));
    return () => document.body.classList.remove("app-shell");
  }, []);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    if (!preview) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPreview(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [preview]);

  if (!site || !content) {
    return <main className="wb-main" aria-busy="true"><p className="sb-help" role="status">{note.text || "Loading…"}</p></main>;
  }
  const live = site.is_published;
  const hint = ACTION_HINTS[content.action.type];

  const edit = (change: Partial<Content>) => { setContent({ ...content, ...change }); setDirty(true); setNote({ text: "You have changes that are not saved yet.", tone: "" }); };
  const field = (key: keyof Content) => ({
    value: (content[key] as string) ?? "",
    onChange: (e: { target: { value: string } }) => edit({ [key]: e.target.value } as Partial<Content>),
  });

  function pickImage(): Promise<string | null> {
    return new Promise((resolve) => {
      pickResolve.current = resolve;
      if (fileInput.current) { fileInput.current.value = ""; fileInput.current.click(); }
    });
  }
  async function onFile() {
    const original = fileInput.current?.files?.[0];
    const done = pickResolve.current;
    if (!original) return done?.(null);
    setNote({ text: "Preparing photo…", tone: "" });
    const file = await shrinkImage(original);
    if (file.size > 2 * 1024 * 1024) { setNote({ text: "That image is still larger than 2 MB. Choose a smaller one.", tone: "error" }); return done?.(null); }
    const form = new FormData();
    form.append("image", file);
    setNote({ text: "Uploading photo…", tone: "" });
    try {
      const r = await api.post<{ url: string }>("/api/website/media", form);
      setNote({ text: "Photo added.", tone: "ok" });
      done?.(r.url);
    } catch (err) {
      setNote({ text: err instanceof ApiError ? err.message : "Could not upload that image.", tone: "error" });
      done?.(null);
    }
  }

  async function saveDraft(quiet: boolean): Promise<boolean> {
    try {
      const r = await api.put<SiteResponse>("/api/website", content);
      setSite(r.website);
      setContent(r.website.content);
      setDirty(false);
      const errs = r.errors ?? {};
      setErrors(errs);
      if (Object.keys(errs).length) {
        setNote({ text: "Saved, but some details need fixing (shown in red).", tone: "error" });
        const known = new Set(["whatsapp", "phone", "email", "action", "services"]);
        const others = Object.entries(errs).filter(([k]) => !known.has(k)).map(([, m]) => m);
        setProblems(others.length ? { title: "Please check:", items: others } : null);
        return false;
      }
      setProblems(null);
      if (!quiet) setNote({ text: "Draft saved. Publish when you are ready.", tone: "ok" });
      return true;
    } catch (err) {
      setNote({ text: err instanceof ApiError ? err.message : "Could not save. Check your connection and try again.", tone: "error" });
      return false;
    }
  }

  async function guarded(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try { await task(); } catch { setNote({ text: "Something went wrong. Check your connection and try again.", tone: "error" }); } finally { setBusy(false); }
  }

  const save = () => guarded(async () => { await saveDraft(false); });
  const openPreview = () => guarded(async () => { if (dirty || !site.exists) await saveDraft(true); setPreview(true); });
  const publish = () => guarded(async () => {
    if (!(await saveDraft(true))) return;
    try {
      const r = await api.post<SiteResponse>("/api/website/publish");
      setSite(r.website);
      setContent(r.website.content);
      setProblems(null);
      setNote({ text: `Your website is live at ${r.website.address}`, tone: "ok" });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as SiteResponse | undefined) : undefined;
      setProblems({ title: body?.message || "Your website is not ready to publish yet.", items: body?.problems ?? [] });
      setNote({ text: "Not published yet. See what is missing above.", tone: "error" });
    }
  });
  const unpublish = () => {
    if (!window.confirm('Take your website offline? Visitors will see a "not found" page until you publish again. Your draft is kept.')) return;
    void guarded(async () => {
      try {
        const r = await api.post<SiteResponse>("/api/website/unpublish");
        setSite(r.website);
        setNote({ text: "Your website is offline.", tone: "ok" });
      } catch (err) { setNote({ text: err instanceof ApiError ? err.message : "Could not take the website offline.", tone: "error" }); }
    });
  };
  async function copy() {
    try { await navigator.clipboard.writeText(site!.url); setCopied(true); } catch { window.prompt("Copy your website link:", site!.url); }
    window.setTimeout(() => setCopied(false), 1800);
  }

  async function toggleProduct(p: SiteProduct, show: boolean) {
    try {
      const r = await api.put<SiteResponse>(`/api/website/products/${p.id}`, { show_on_website: show });
      setSite({ ...site!, products: r.website.products, publish_problems: r.website.publish_problems });
      setNote({ text: show ? "Product is shown on your website." : "Product is hidden from your website.", tone: "ok" });
    } catch (err) { setNote({ text: err instanceof ApiError ? err.message : "Could not update that product.", tone: "error" }); }
  }
  async function productImage(p: SiteProduct) {
    const url = await pickImage();
    if (!url) return;
    try {
      const r = await api.put<SiteResponse>(`/api/website/products/${p.id}`, { image_url: url });
      setSite({ ...site!, products: r.website.products });
    } catch (err) { setNote({ text: err instanceof ApiError ? err.message : "Could not save that photo.", tone: "error" }); }
  }

  const setService = (i: number, change: Partial<Service>) =>
    edit({ services: content.services.map((s, j) => (j === i ? { ...s, ...change } : s)) });
  const moveService = (i: number, by: number) => {
    const t = i + by;
    if (t < 0 || t >= content.services.length) return;
    const next = [...content.services];
    [next[i], next[t]] = [next[t], next[i]];
    edit({ services: next });
  };
  const err = (key: string) => errors[key] && <p className="sb-error" data-error={key}>{errors[key]}</p>;
  const thumbStyle = (url: string) => (url ? { backgroundImage: `url("${url}")` } : undefined);
  const isProduct = content.layout === "product";
  const showProfileLogo = Boolean(site.profile_logo) && content.logo_url !== site.profile_logo;

  return (
    <>
      <header className="wb-top">
        <div className="wb-top-row">
          <Link className="wb-back" to="/dashboard">
            <svg className="w-5 h-5" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="m15 6-6 6 6 6" /></svg>
            Back
          </Link>
          <h1>Website</h1>
        </div>
      </header>

      <main className="wb-main" id="wb-main" aria-busy={busy}>
        <section className="sb-panel" aria-labelledby="status-title">
          <h2 id="status-title" className="sr-only">Website address and status</h2>
          <p className="sb-help">Your website address</p>
          <p className="wb-status-address">{site.address}</p>
          <p style={{ marginTop: 6 }}>
            <span className={`wb-badge ${live ? (site.has_unpublished_changes ? "wb-badge-changes" : "wb-badge-live") : "wb-badge-off"}`}>
              {live ? (site.has_unpublished_changes ? "Live · changes not published" : "Live") : "Not published"}
            </span>{" "}
            <span className="sb-help">{live ? (site.has_unpublished_changes ? "Visitors still see the last published version." : "") : "Nobody can see your website until you publish."}</span>
          </p>
          {live && (
            <div className="wb-status-actions">
              <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={copy}>{copied ? "Copied" : "Copy link"}</button>
              <a className="sb-btn sb-btn-small sb-btn-secondary" href={site.url} target="_blank" rel="noopener">Open website</a>
              <button type="button" className="sb-btn sb-btn-small sb-btn-danger-text" onClick={unpublish}>Take offline</button>
            </div>
          )}
          <p className="sb-help" style={{ marginTop: 10 }}>The address is set for you and stays the same. {site.store_url ? "Your shop link keeps working as before." : ""}</p>
        </section>

        <section className="sb-panel" aria-labelledby="step-layout">
          <h2 className="wb-step-title" id="step-layout"><span>1</span> Choose a layout</h2>
          <p className="wb-step-sub">Pick the one that fits your business. You can switch later.</p>
          <div className="wb-layouts" role="radiogroup" aria-labelledby="step-layout">
            <label className="wb-layout">
              <input type="radio" name="layout" value="product" checked={isProduct} onChange={() => edit({ layout: "product" })} />
              <div className="wb-wire" aria-hidden="true"><i className="hero" /><div className="cards"><i /><i /><i /></div><div className="cards"><i /><i /><i /></div></div>
              <strong>Product Store</strong>
              <p>For shops that sell items. Shows your products and prices from Inventory.</p>
            </label>
            <label className="wb-layout">
              <input type="radio" name="layout" value="service" checked={!isProduct} onChange={() => edit({ layout: "service" })} />
              <div className="wb-wire" aria-hidden="true"><i className="hero" /><i className="cta" /><div className="rows"><i /><i /><i /></div></div>
              <strong>Service Business</strong>
              <p>For salons, tailors, repairs and more. Lists your services with a booking button.</p>
            </label>
          </div>
        </section>

        <section className="sb-panel" aria-labelledby="step-details">
          <h2 className="wb-step-title" id="step-details"><span>2</span> Business details</h2>
          <p className="wb-step-sub">Everything you fill in here is shown on your public website. Leave a box empty to keep it off the site.</p>
          <div className="wb-fields">
            <div className="sb-field">
              <label htmlFor="f-display_name">Business name <span className="wb-public">Public</span></label>
              <input id="f-display_name" type="text" maxLength={80} autoComplete="organization" {...field("display_name")} />
            </div>
            <div className="sb-field">
              <label htmlFor="f-tagline">Short description <span className="sb-optional">(optional)</span></label>
              <input id="f-tagline" type="text" maxLength={160} placeholder="e.g. Streetwear made in Lagos" {...field("tagline")} />
              <p className="sb-help">One line under your name at the top of the site.</p>
            </div>
            <div className="sb-field">
              <label>Logo <span className="sb-optional">(optional)</span></label>
              <div className="wb-image-row">
                <div className={`wb-thumb ${content.logo_url ? "has-image" : ""}`} style={thumbStyle(content.logo_url)}>No logo</div>
                <div className="wb-image-buttons">
                  <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={async () => { const u = await pickImage(); if (u) edit({ logo_url: u }); }}>Upload</button>
                  {showProfileLogo && <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={() => edit({ logo_url: site.profile_logo })}>Use profile logo</button>}
                  {content.logo_url && <button type="button" className="sb-btn sb-btn-small sb-btn-danger-text" onClick={() => edit({ logo_url: "" })}>Remove</button>}
                </div>
              </div>
            </div>
            <div className="sb-field">
              <label>Cover photo <span className="sb-optional">(optional)</span></label>
              <div className="wb-image-row">
                <div className={`wb-thumb wide ${content.cover_url ? "has-image" : ""}`} style={thumbStyle(content.cover_url)}>No photo</div>
                <div className="wb-image-buttons">
                  <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" onClick={async () => { const u = await pickImage(); if (u) edit({ cover_url: u }); }}>Upload</button>
                  {content.cover_url && <button type="button" className="sb-btn sb-btn-small sb-btn-danger-text" onClick={() => edit({ cover_url: "" })}>Remove</button>}
                </div>
              </div>
              <p className="sb-help">A wide photo behind your name. Without one, the site uses a clean text header.</p>
            </div>
            <div className="sb-field">
              <label htmlFor="f-brand_color">Brand colour</label>
              <div className="wb-color-row">
                <input id="f-brand_color" type="color" aria-label="Brand colour" {...field("brand_color")} />
                <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {SWATCHES.map((c) => <button key={c} type="button" className="wb-swatch" style={{ background: c }} aria-label={`Use colour ${c}`} onClick={() => edit({ brand_color: c })} />)}
                </span>
              </div>
              <p className="sb-help">Used for buttons and accents. Text colour adjusts so it stays readable.</p>
            </div>
            <div className="sb-field">
              <label htmlFor="f-about">About your business <span className="sb-optional">(optional)</span></label>
              <textarea id="f-about" maxLength={1200} rows={4} placeholder="What you do, how long you've been doing it, what makes you different." {...field("about")} />
            </div>
            <div className="sb-field-row sb-field-row-stack">
              <div className="sb-field">
                <label htmlFor="f-whatsapp">WhatsApp number <span className="sb-optional">(optional)</span></label>
                <input id="f-whatsapp" type="tel" inputMode="tel" placeholder="+2348012345678" {...field("whatsapp")} />
                {err("whatsapp")}
              </div>
              <div className="sb-field">
                <label htmlFor="f-phone">Phone number <span className="sb-optional">(optional)</span></label>
                <input id="f-phone" type="tel" inputMode="tel" placeholder="+2348012345678" {...field("phone")} />
                {err("phone")}
              </div>
            </div>
            <div className="sb-field-row sb-field-row-stack">
              <div className="sb-field">
                <label htmlFor="f-email">Email <span className="sb-optional">(optional)</span></label>
                <input id="f-email" type="email" placeholder="you@example.com" {...field("email")} />
                {err("email")}
              </div>
              <div className="sb-field">
                <label htmlFor="f-instagram">Instagram <span className="sb-optional">(optional)</span></label>
                <input id="f-instagram" type="text" placeholder="aisha_wears" {...field("instagram")} />
              </div>
            </div>
            <div className="sb-field">
              <label htmlFor="f-address">Location <span className="sb-optional">(optional)</span></label>
              <input id="f-address" type="text" maxLength={200} placeholder="12 Market St, Lagos" {...field("address")} />
            </div>
            <div className="sb-field">
              <label htmlFor="f-hours">Opening hours <span className="sb-optional">(optional)</span></label>
              <textarea id="f-hours" maxLength={300} rows={2} placeholder="Mon–Sat 9am–7pm" {...field("hours")} />
            </div>
          </div>
        </section>

        <section className="sb-panel" aria-labelledby="step-content">
          <h2 className="wb-step-title" id="step-content"><span>3</span> <span style={{ fontSize: "inherit", color: "inherit", fontWeight: "inherit" }}>{isProduct ? "Products" : "Services"}</span></h2>
          {isProduct ? (
            <div>
              <p className="wb-step-sub">These come from your Inventory. Changes to products show on a live site straight away. <Link className="sb-link" to="/inventory" style={{ padding: 0 }}>Manage products</Link></p>
              <div>
                {site.products.length === 0 && <p className="list-empty" style={{ padding: "16px 0" }}>You have no products yet. <Link className="sb-link" to="/inventory">Add products in Inventory</Link></p>}
                {site.products.map((p) => (
                  <div className="wb-item" key={p.id}>
                    <button type="button" className={`wb-thumb ${p.image_url ? "has-image" : ""}`} style={thumbStyle(p.image_url)} aria-label={`Photo for ${p.name}`} onClick={() => productImage(p)}>Photo</button>
                    <div className="wb-item-text"><strong>{p.name}</strong><span>{money(p.price)}{p.sold_out ? " · Sold out" : ""}</span></div>
                    <label className="wb-switch"><input type="checkbox" checked={p.show_on_website} onChange={(e) => toggleProduct(p, e.target.checked)} /> Show</label>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <p className="wb-step-sub">List what you offer. Leave the price empty if you quote each customer.</p>
              <div className="wb-fields">
                {content.services.length === 0 && <p className="sb-help">No services yet. Add your first one below.</p>}
                {content.services.map((s, i) => (
                  <div className="wb-service" key={i}>
                    <div className="wb-service-head">
                      <span>Service {i + 1}</span>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button type="button" className="sb-icon-btn" aria-label="Move up" disabled={i === 0} onClick={() => moveService(i, -1)}>↑</button>
                        <button type="button" className="sb-icon-btn" aria-label="Move down" disabled={i === content.services.length - 1} onClick={() => moveService(i, 1)}>↓</button>
                        <button type="button" className="sb-icon-btn" aria-label="Remove service" onClick={() => edit({ services: content.services.filter((_, j) => j !== i) })}>×</button>
                      </div>
                    </div>
                    <div className="sb-field"><label>Name</label><input type="text" maxLength={80} value={s.name} placeholder="e.g. Knotless braids" onChange={(e) => setService(i, { name: e.target.value })} /></div>
                    <div className="sb-field"><label>Short description <span className="sb-optional">(optional)</span></label><input type="text" maxLength={300} value={s.description ?? ""} onChange={(e) => setService(i, { description: e.target.value })} /></div>
                    <div className="sb-field-row">
                      <div className="sb-field"><label>Price (₦) <span className="sb-optional">(optional)</span></label>
                        <input type="number" inputMode="decimal" min={0} step="any" value={s.price ?? ""} onChange={(e) => setService(i, { price: e.target.value === "" ? null : e.target.value })} /></div>
                      <div className="sb-field"><label>Photo <span className="sb-optional">(optional)</span></label>
                        <div className="wb-image-row">
                          <button type="button" className={`wb-thumb ${s.image_url ? "has-image" : ""}`} style={{ width: 46, height: 46, ...thumbStyle(s.image_url) }} aria-label="Service photo"
                            onClick={async () => { const u = await pickImage(); if (u) setService(i, { image_url: u }); }}>+</button>
                          {s.image_url && <button type="button" className="sb-link" onClick={() => setService(i, { image_url: "" })}>Remove</button>}
                        </div></div>
                    </div>
                  </div>
                ))}
              </div>
              {err("services")}
              <button type="button" className="sb-btn sb-btn-secondary" style={{ marginTop: 12, width: "100%" }}
                onClick={() => content.services.length >= 30 ? setNote({ text: "You can list up to 30 services.", tone: "error" }) : edit({ services: [...content.services, { name: "", description: "", price: null, image_url: "" }] })}>+ Add a service</button>
            </div>
          )}
          <div style={{ marginTop: 18 }}>
            <p className="sb-field"><label>{isProduct ? "Gallery" : "Photos of your work"} <span className="sb-optional">(optional, up to 12 photos)</span></label></p>
            <div className="wb-gallery" style={{ marginTop: 8 }}>
              {content.gallery.map((url, i) => (
                <div key={url + i} className="wb-gallery-item" style={{ backgroundImage: `url('${url}')` }}>
                  <button type="button" aria-label={`Remove photo ${i + 1}`} onClick={() => edit({ gallery: content.gallery.filter((_, j) => j !== i) })}>×</button>
                </div>
              ))}
            </div>
            {content.gallery.length < 12 && (
              <button type="button" className="sb-btn sb-btn-small sb-btn-secondary" style={{ marginTop: 8 }}
                onClick={async () => { const u = await pickImage(); if (u) edit({ gallery: [...content.gallery, u] }); }}>+ Add photo</button>
            )}
          </div>
        </section>

        <section className="sb-panel" aria-labelledby="step-action">
          <h2 className="wb-step-title" id="step-action"><span>4</span> Main button</h2>
          <p className="wb-step-sub">The one thing you want visitors to do. It stays in reach on phones.</p>
          <div className="wb-fields">
            <div className="sb-field">
              <label htmlFor="f-action-type">What should it do?</label>
              <select id="f-action-type" value={content.action.type} onChange={(e) => edit({ action: { ...content.action, type: e.target.value as Action["type"] } })}>
                <option value="whatsapp">Open a WhatsApp chat</option>
                <option value="call">Call a phone number</option>
                <option value="link">Open a link (booking or quote form)</option>
              </select>
            </div>
            <div className="sb-field">
              <label htmlFor="f-action-value">{hint.label}</label>
              <input id="f-action-value" type="text" placeholder={hint.placeholder} inputMode={content.action.type === "link" ? "url" : "tel"}
                value={content.action.value} onChange={(e) => edit({ action: { ...content.action, value: e.target.value } })} />
              {err("action")}
            </div>
            <div className="sb-field">
              <label htmlFor="f-action-label">Button text <span className="sb-optional">(optional)</span></label>
              <input id="f-action-label" type="text" maxLength={30} placeholder={hint.text}
                value={content.action.label} onChange={(e) => edit({ action: { ...content.action, label: e.target.value } })} />
            </div>
          </div>
        </section>

        {problems && problems.items.length > 0 && (
          <div className="wb-problems" role="alert"><strong>{problems.title}</strong><ul>{problems.items.map((p) => <li key={p}>{p}</li>)}</ul></div>
        )}
        {problems && problems.items.length === 0 && <div className="wb-problems" role="alert"><strong>{problems.title}</strong></div>}
      </main>

      <div className="wb-bar">
        <p className="wb-bar-note" aria-live="polite" style={{ color: note.tone === "error" ? "#be123c" : note.tone === "ok" ? "#047857" : undefined }}>{note.text}</p>
        <div className="wb-bar-row">
          <button type="button" className="sb-btn sb-btn-secondary" disabled={busy} onClick={save}>{busy ? "Working…" : "Save draft"}</button>
          <button type="button" className="sb-btn sb-btn-secondary" disabled={busy} onClick={openPreview}>Preview</button>
          <button type="button" className="sb-btn sb-btn-primary" disabled={busy} onClick={publish}>{live ? "Publish changes" : "Publish"}</button>
        </div>
      </div>

      {preview && (
        <div id="preview-modal" className="sb-modal" role="dialog" aria-modal="true" aria-labelledby="preview-title" onMouseDown={(e) => e.target === e.currentTarget && setPreview(false)}>
          <div className="sb-sheet">
            <div className="sb-sheet-head">
              <div>
                <h3 id="preview-title" className="sb-sheet-title">Preview</h3>
                <p className="sb-sheet-sub">How your draft looks on a phone. Only you can see it. <a className="sb-link" style={{ padding: 0 }} href="/website/preview" target="_blank" rel="noopener">Open full size</a></p>
              </div>
              <button type="button" className="sb-icon-btn" aria-label="Close preview" onClick={() => setPreview(false)}>
                <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M6 6l12 12M18 6 6 18" /></svg>
              </button>
            </div>
            <div className="wb-preview-body"><iframe title="Website preview" src={`/website/preview?t=${Date.now()}`} /></div>
          </div>
        </div>
      )}
      <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={onFile} />
    </>
  );
}
