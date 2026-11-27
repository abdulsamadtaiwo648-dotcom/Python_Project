import EmptyState from "../components/EmptyState";
import Skeleton from "../components/Skeleton";
import { useEffect, useMemo, useState } from "react";
import { UpgradeNotice } from "../components/Upgrade";
import { NewSale, SettleDebt, type Receipt, type Status } from "../components/SaleSheets";
import ImportSheet from "../components/ImportSheet";
import { useData } from "../data";
import { useSession } from "../session";
import { dateTimeLabel, money, parseSaved, relativeDay } from "../format";
import { dayOf } from "../analytics";
import type { BusinessProfile, Sale } from "../types";
import { escapeHtml } from "../escape";
import { useToast } from "../ui/Toast";
import { FilterChips, SelectSheet } from "../ui";
import Sheet from "../components/Sheet";
import FAB from "../ui/FAB";
import { useOpenNew } from "../ui/useOpenNew";
import { SyncPending } from "../ui";

type Quick = "all" | "today" | "week" | "bulk";
const STATUS: Record<Status, { label: string; cls: string }> = {
  paid: { label: "Paid", cls: "sale-badge-paid" },
  partial: { label: "Part-paid", cls: "sale-badge-partial" },
  unpaid: { label: "Unpaid", cls: "sale-badge-unpaid" },
};


function groupReceipts(sales: Sale[]): Receipt[] {
  const map = new Map<string, Sale[]>();
  for (const s of sales) {
    const key = s.checkout_id ? `c:${s.checkout_id}` : `r:${s.id}`;
    map.set(key, [...(map.get(key) ?? []), s]);
  }
  return [...map.entries()].map(([key, items]) => {
    items.sort((a, b) => a.id - b.id);
    const total = items.reduce((n, s) => n + s.total_value, 0);
    const paid = items.reduce((n, s) => n + s.amount_paid, 0);
    const owed = Math.max(total - paid, 0);
    return { key, items, total, paid, owed, status: owed <= 0 ? "paid" : paid > 0 ? "partial" : "unpaid" };
  });
}

const lineTitle = (s: Sale) => {
  if (s.sale_type === "bulk" && s.bundle_count) {
    const size = s.bundle_size || Math.round(s.quantity / s.bundle_count);
    return `${s.bundle_count} bulk x ${s.description} (${size} pcs each)`;
  }
  return s.quantity > 1 ? `${s.quantity} x ${s.description}` : s.description;
};
const saleDate = (v: string) => {
  const d = parseSaved(v);
  return d ? dateTimeLabel(v) : v;
};

function printReceipt(r: Receipt, profile: BusinessProfile | null, branded: boolean) {
  const w = window.open("", "_blank", "width=420,height=640");
  if (!w) return;
  const esc = escapeHtml;
  const first = r.items[0];
  w.document.write(`<!doctype html><title>Receipt ${esc(first.receipt_id)}</title>
<style>body{font:14px Inter,system-ui,sans-serif;padding:24px;color:#0f172a}h1{font-size:18px;margin:0}p{margin:2px 0;color:#475569}
table{width:100%;border-collapse:collapse;margin:16px 0}td{padding:6px 0;border-bottom:1px solid #e2e8f0}td:last-child{text-align:right}
.t td{font-weight:700;border:0}</style>
${branded && profile?.logo_url ? `<img src="${esc(window.location.origin + profile.logo_url)}" alt="" style="height:48px;margin-bottom:8px">` : ""}<h1>${esc(profile?.company_name || "SoloBiz")}</h1>
<p>${esc(profile?.business_address || "")}</p><p>${esc(profile?.business_phone || "")}</p>
<p style="margin-top:12px">Receipt #${esc(first.receipt_id)} · ${esc(saleDate(first.date))}</p>
<p>Customer: ${esc(first.customer_name)} · ${esc(first.payment_mode)}</p>
<table>${r.items.map((s) => `<tr><td>${esc(lineTitle(s))}</td><td>${esc(money(s.total_value))}</td></tr>`).join("")}
<tr class="t"><td>Total</td><td>${esc(money(r.total))}</td></tr>
<tr class="t"><td>Paid</td><td>${esc(money(r.paid))}</td></tr>
${r.owed > 0 ? `<tr class="t"><td>Balance due</td><td>${esc(money(r.owed))}</td></tr>` : ""}</table>
<p>Thank you for your business.</p>${branded ? "" : '<p style="margin-top:16px;font-size:11px;color:#94a3b8">Receipt made with SoloBiz</p>'}`);
  w.document.close();
  w.focus();
  w.print();
}

export default function Sales() {
  const { sales, products, profile, write, subscription, can, reload, loading } = useData();
  const { access } = useSession();
  const canDelete = !access || access.is_owner;
  const [quick, setQuick] = useState<Quick>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [product, setProduct] = useState("");
  const [payment, setPayment] = useState("");
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");
  const [creating, setCreating] = useState(false);
  useOpenNew(() => setCreating(true));
  const [importing, setImporting] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const [settling, setSettling] = useState<Receipt | null>(null);
  // Receipts deleted but not yet confirmed. Hidden now; the delete is sent after five seconds unless Undo is tapped.
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const toast = useToast();
  const [needProfile, setNeedProfile] = useState(false);
  const [detail, setDetail] = useState<Receipt | null>(null);

  useEffect(() => { document.title = "Sales | SoloBiz"; }, []);
  // On phones the New sale form is a full-screen sheet: Escape closes it and the page behind does not scroll.
  useEffect(() => {
    if (!creating || !window.matchMedia("(max-width: 1023px)").matches) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setCreating(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [creating]);

  const names = useMemo(() => [...new Set(sales.map((s) => s.description.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b)), [sales]);

  const receipts = useMemo(() => {
    const todayKey = new Date().toDateString();
    const weekStart = new Date(Date.now() - 7 * 86_400_000);
    let list = sales;
    if (quick === "today") list = list.filter((s) => parseSaved(s.date)?.toDateString() === todayKey);
    if (quick === "week") list = list.filter((s) => (parseSaved(s.date) ?? 0) >= weekStart);
    if (quick === "bulk") list = list.filter((s) => s.sale_type === "bulk");
    if (product) list = list.filter((s) => s.description.trim() === product);
    return groupReceipts(list)
      .filter((r) => !payment || r.status === payment)
      .filter((r) => min === "" || r.total >= Number(min))
      .filter((r) => max === "" || r.total <= Number(max))
      .sort((a, b) => b.items[0].id - a.items[0].id);
  }, [sales, quick, product, payment, min, max]);

  const totalReceipts = useMemo(() => groupReceipts(sales).length, [sales]);
  // Receipts grouped by business day, newest day first, with the day's total.
  const dayGroups = useMemo(() => {
    const groups = new Map<string, { day: string; label: string; total: number; items: Receipt[] }>();
    for (const r of receipts.filter((x) => !hidden.has(x.key))) {
      const first = r.items[0];
      const day = dayOf(first) || first.date.slice(0, 10);
      const group = groups.get(day) ?? { day, label: relativeDay(first.entry_date || first.date), total: 0, items: [] };
      group.total += r.total;
      group.items.push(r);
      groups.set(day, group);
    }
    return [...groups.values()];
  }, [receipts, hidden]);

  const activeFilters = [product, payment, min, max].filter((v) => v !== "").length;
  const filtered = quick !== "all" || activeFilters > 0;

  function removeSale(r: Receipt) {
    setHidden((h) => new Set(h).add(r.key));
    const unhide = () => setHidden((h) => { const n = new Set(h); n.delete(r.key); return n; });
    const timer = window.setTimeout(() => {
      const stock: Record<number, number> = {};
      for (const s of r.items) {
        if (s.inventory_item_id != null) stock[s.inventory_item_id] = (stock[s.inventory_item_id] ?? 0) + s.quantity;
      }
      write({ kind: "sale_delete", method: "DELETE", url: `/api/income/${r.items[0].id}`,
        meta: { saleIds: r.items.map((s) => s.id), checkoutId: r.items[0].checkout_id, stock } })
        .catch(() => { unhide(); toast({ text: "Could not delete that sale. It is back in your list." }); });
    }, 5000);
    toast({ text: "Sale deleted.", actionLabel: "Undo", onAction: () => { window.clearTimeout(timer); unhide(); } });
  }


  return (
    <section id="tab-income-content" className="tab-content page-stack" aria-labelledby="sales-title">
      <div className="page-head">
        <div className="min-w-0"><h2 className="page-title" id="sales-title">Sales</h2><p className="page-sub">Record every sale, unit or bulk.</p></div>
        <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setImporting(true)}>Import CSV</button>
        <button type="button" id="btn-new-sale" className="sb-btn sb-btn-primary" onClick={() => setCreating(true)}>
          <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path d="M12 5v14M5 12h14" /></svg>
          New sale
        </button>
      </div>

      {subscription?.current.history_days != null && (
        <UpgradeNotice title={`Showing the last ${subscription.current.history_days} days of sales`}
          text="Older sales are kept safely. A longer history comes with a paid plan." plan="Basic" />
      )}
      <div id="sales-main-view" className="page-stack">
        {/* A side panel on desktop; a full-screen sheet on phones. */}
        <div id="sale-entry-modal" className={creating ? "sb-modal" : "sb-modal hidden"} role="dialog" aria-modal="true" aria-labelledby="sale-modal-title">
          <NewSale key={formKey} products={products} onClose={() => setCreating(false)}
            onDone={() => { setCreating(false); setFormKey((k) => k + 1); }} />
        </div>
        {importing && <ImportSheet kind="sales" onDone={() => void reload()} onClose={() => setImporting(false)} />}
        <div id="sales-quick-filters" className="flex flex-wrap items-center gap-2" role="group" aria-label="Quick filters">
          <div className="list-toolbar sales-toolbar-inline">
            <button type="button" className="sb-chip" aria-expanded={filterOpen} aria-controls="sales-filter-panel" onClick={() => setFilterOpen(!filterOpen)}>
              <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M4 6h16M7 12h10M10 18h4" /></svg>
              Filter {activeFilters > 0 && <span className="sb-chip-count">{activeFilters}</span>}
            </button>
            <p className="list-toolbar-text" aria-live="polite">
              {filtered ? `Showing ${receipts.length} of ${totalReceipts} sales` : `${totalReceipts} ${totalReceipts === 1 ? "sale" : "sales"}`}
            </p>
            {filtered && <button type="button" className="sb-link" onClick={() => { setQuick("all"); setProduct(""); setPayment(""); setMin(""); setMax(""); }}>Clear</button>}
          </div>
          <FilterChips label="Filter by payment" value={payment} onChange={setPayment}
            options={[{ value: "", label: "All" }, { value: "paid", label: "Paid" }, { value: "partial", label: "Part-paid" }, { value: "unpaid", label: "Owing" }]} />
        </div>

        {filterOpen && (
          <section id="sales-filter-panel" className="sb-panel filter-panel is-open" aria-label="Filter sales">
            <div className="filter-grid">
              <div className="sb-field"><label htmlFor="sales-product-filter">Product</label>
                <select id="sales-product-filter" value={product} onChange={(e) => setProduct(e.target.value)}>
                  <option value="">All products</option>{names.map((n) => <option key={n}>{n}</option>)}
                </select></div>
              <SelectSheet<Quick> label="When" value={quick} placeholder="All time"
                options={[{ value: "all", label: "All time" }, { value: "today", label: "Today" }, { value: "week", label: "This week" }, { value: "bulk", label: "Bulk sales" }]}
                onChange={setQuick} />
              <div className="sb-field"><label htmlFor="sales-min-total">Sale total from (₦)</label>
                <input id="sales-min-total" type="number" min={0} step="0.01" inputMode="decimal" placeholder="Any" value={min} onChange={(e) => setMin(e.target.value)} /></div>
              <div className="sb-field"><label htmlFor="sales-max-total">Sale total up to (₦)</label>
                <input id="sales-max-total" type="number" min={0} step="0.01" inputMode="decimal" placeholder="Any" value={max} onChange={(e) => setMax(e.target.value)} /></div>
            </div>
          </section>
        )}

        <div id="income-list" className="sale-list" aria-live="polite">
          {loading && sales.length === 0 && <Skeleton rows={4} label="Loading sales" />}
          {!loading && receipts.length === 0 && (
            sales.length === 0
              ? <EmptyState message="No sales yet." action={<button type="button" className="sb-btn sb-btn-primary" onClick={() => setCreating(true)}>New sale</button>} />
              : <p className="list-empty">No sales match these filters.</p>
          )}
          {dayGroups.map((g) => (
            <section key={g.day} aria-label={g.label}>
              <div className="ui-day-head"><span>{g.label}</span><span>{money(g.total)}</span></div>
              {g.items.map((r) => {
            const first = r.items[0];
            const meta = [saleDate(first.date), first.payment_mode || "Cash", first.receipt_id ? `#${first.receipt_id}` : ""].filter(Boolean).join(" · ");
            return (
              <article key={r.key} className="sale-card">
                <div className="sale-card-top">
                  <button type="button" className="min-w-0 text-left" onClick={() => setDetail(r)} aria-label={`Details for ${first.customer_name || "walk-in customer"}`}>
                    <p className="sale-customer">{first.customer_name || "Walk-in customer"}{r.items.some((x) => x.pending) && <span className="ml-1"><SyncPending /></span>}</p>
                    <p className="sale-meta">{meta}</p>
                  </button>
                  <div className="sale-total">
                    <p>{money(r.total)}</p>
                    <span className={`sale-badge ${STATUS[r.status].cls}`}>{STATUS[r.status].label}</span>
                  </div>
                </div>
                <ul className="sale-items">
                  {r.items.map((s) => <li key={s.id}><span>{lineTitle(s)}</span><span>{money(s.total_value)}</span></li>)}
                </ul>
                {r.owed > 0 && <p className="sale-owed">{money(r.owed)} still owed · {money(r.paid)} paid</p>}
                <div className="sale-actions">
                  {r.owed > 0 && <button type="button" className="btn-settle-debt sb-btn sb-btn-small sb-btn-warn" onClick={() => setSettling(r)}>Record payment</button>}
                  <button type="button" className="sb-btn sb-btn-small sb-btn-secondary"
                    onClick={() => (profile?.company_name ? printReceipt(r, profile, can("branding")) : setNeedProfile(true))}>Receipt</button>
                  {canDelete && (
                                    <button type="button" className="btn-delete-income sb-btn sb-btn-small sb-btn-danger-text" aria-label="Delete this sale"
                    onClick={() => removeSale(r)}>Delete</button>
                  )}
                </div>
              </article>
            );
              })}
            </section>
          ))}
        </div>
        <FAB label="New sale" onClick={() => setCreating(true)} />
      </div>

      {settling && <SettleDebt receipt={settling} onClose={() => setSettling(null)} />}
      {detail && (
        <Sheet title="Sale details" onClose={() => setDetail(null)} compact>
          <div className="sb-sheet-body">
            <p className="sale-customer">{detail.items[0].customer_name || "Walk-in customer"}</p>
            <p className="sale-meta">{saleDate(detail.items[0].date)} · {detail.items[0].payment_mode || "Cash"}{detail.items[0].receipt_id ? ` · #${detail.items[0].receipt_id}` : ""}</p>
            <ul className="sale-items" style={{ marginTop: 12 }}>
              {detail.items.map((s) => <li key={s.id}><span>{lineTitle(s)}</span><span>{money(s.total_value)}</span></li>)}
            </ul>
            <dl style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 6, marginTop: 12, fontSize: "var(--sb-text-body)" }}>
              <dt>Total</dt><dd style={{ margin: 0, fontWeight: 700 }}>{money(detail.total)}</dd>
              <dt>Paid so far</dt><dd style={{ margin: 0 }}>{money(detail.paid)}</dd>
              <dt>Still owed</dt><dd style={{ margin: 0, fontWeight: 700, color: detail.owed > 0 ? "var(--sb-warning)" : undefined }}>{money(detail.owed)}</dd>
            </dl>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
              {detail.owed > 0 && <button type="button" className="sb-btn sb-btn-primary" onClick={() => { setSettling(detail); setDetail(null); }}>Record payment</button>}
              <a className="sb-btn sb-btn-secondary" target="_blank" rel="noopener"
                href={`https://wa.me/?text=${encodeURIComponent(`Receipt ${detail.items[0].receipt_id || ""}: ${money(detail.total)}. Thank you!`)}`}>Share on WhatsApp</a>
              <button type="button" className="sb-btn sb-btn-secondary"
                onClick={() => (profile?.company_name ? printReceipt(detail, profile, can("branding")) : setNeedProfile(true))}>Print receipt</button>
              {canDelete && <button type="button" className="sb-btn sb-btn-danger-text" onClick={() => { removeSale(detail); setDetail(null); }}>Delete</button>}
            </div>
          </div>
        </Sheet>
      )}
      {needProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="w-full max-w-sm rounded-3xl border border-slate-100 bg-white p-6 shadow-2xl">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-700">Receipt setup required</p>
            <h3 className="mt-1 text-xl font-black text-slate-900">Add your business profile first</h3>
            <p className="mt-2 text-sm text-slate-600">Receipts carry your business name, address and phone number.</p>
            <div className="mt-6 flex gap-3">
              <button type="button" className="flex-1 rounded-xl bg-slate-100 py-3 text-xs font-black text-slate-700" onClick={() => setNeedProfile(false)}>Not now</button>
              <a href="/profile" className="flex-1 rounded-xl bg-blue-700 py-3 text-center text-xs font-black text-white no-underline">Open profile</a>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
