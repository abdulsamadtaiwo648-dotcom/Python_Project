import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../api";
import Sheet from "../components/Sheet";
import { useData } from "../data";
import { money, parseSaved } from "../format";
import { nextTempId, nowStamp } from "../offline";
import type { BusinessProfile, Product, Sale } from "../types";

type Quick = "all" | "today" | "week" | "bulk";
type Status = "paid" | "partial" | "unpaid";
const STATUS: Record<Status, { label: string; cls: string }> = {
  paid: { label: "Paid", cls: "sale-badge-paid" },
  partial: { label: "Part-paid", cls: "sale-badge-partial" },
  unpaid: { label: "Unpaid", cls: "sale-badge-unpaid" },
};

interface Receipt { key: string; items: Sale[]; total: number; paid: number; owed: number; status: Status }

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
  return d ? d.toLocaleString("en-NG", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true }) : v;
};

function printReceipt(r: Receipt, profile: BusinessProfile | null) {
  const w = window.open("", "_blank", "width=420,height=640");
  if (!w) return;
  const esc = (t: string) => t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
  const first = r.items[0];
  w.document.write(`<!doctype html><title>Receipt ${esc(first.receipt_id)}</title>
<style>body{font:14px Inter,system-ui,sans-serif;padding:24px;color:#0f172a}h1{font-size:18px;margin:0}p{margin:2px 0;color:#475569}
table{width:100%;border-collapse:collapse;margin:16px 0}td{padding:6px 0;border-bottom:1px solid #e2e8f0}td:last-child{text-align:right}
.t td{font-weight:700;border:0}</style>
<h1>${esc(profile?.company_name || "SoloBiz")}</h1>
<p>${esc(profile?.business_address || "")}</p><p>${esc(profile?.business_phone || "")}</p>
<p style="margin-top:12px">Receipt #${esc(first.receipt_id)} · ${esc(saleDate(first.date))}</p>
<p>Customer: ${esc(first.customer_name)} · ${esc(first.payment_mode)}</p>
<table>${r.items.map((s) => `<tr><td>${esc(lineTitle(s))}</td><td>${esc(money(s.total_value))}</td></tr>`).join("")}
<tr class="t"><td>Total</td><td>${esc(money(r.total))}</td></tr>
<tr class="t"><td>Paid</td><td>${esc(money(r.paid))}</td></tr>
${r.owed > 0 ? `<tr class="t"><td>Balance due</td><td>${esc(money(r.owed))}</td></tr>` : ""}</table>
<p>Thank you for your business.</p>`);
  w.document.close();
  w.focus();
  w.print();
}

interface Line {
  key: string;
  presetId: number | null;
  name: string;
  price: string;
  qty: string;
  bulk: boolean;
}

let lineSeq = 0;
const blankLine = (): Line => ({ key: `l${++lineSeq}`, presetId: null, name: "", price: "", qty: "1", bulk: false });

function NewSale(props: { products: Product[]; onClose: () => void; onDone: () => void }) {
  const { products } = props;
  const { write } = useData();
  const [lines, setLines] = useState<Line[]>([blankLine()]);
  const [customer, setCustomer] = useState("");
  const [mode, setMode] = useState("Cash");
  const [paid, setPaid] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [checkoutId] = useState(() => (crypto.randomUUID ? crypto.randomUUID() : `co-${Date.now()}-${Math.random().toString(36).slice(2)}`));

  const product = (id: number | null) => products.find((p) => p.id === id);
  const unitsUsed = (id: number, skip?: string) =>
    lines.reduce((n, l) => {
      if (l.presetId !== id || l.key === skip) return n;
      const p = product(id);
      const q = Number(l.qty) || 0;
      return n + (l.bulk && p?.bulk_quantity ? q * p.bulk_quantity : q);
    }, 0);
  const limit = (l: Line) => {
    const p = product(l.presetId);
    if (!p || !p.track_stock) return 10000;
    const free = p.stock - unitsUsed(p.id, l.key);
    return l.bulk && p.bulk_quantity ? Math.floor(free / p.bulk_quantity) : free;
  };
  const lineTotal = (l: Line) => (Number(l.price.replace(/,/g, "")) || 0) * (Number(l.qty) || 0);
  const total = lines.reduce((n, l) => n + lineTotal(l), 0);
  const paidValue = paid === null ? total : Number(paid.replace(/,/g, "")) || 0;

  const patch = (key: string, change: Partial<Line>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...change } : l)));

  function addProduct(id: number) {
    const p = product(id);
    if (!p) return;
    if (p.track_stock && unitsUsed(p.id) >= p.stock) return window.alert(`Only ${p.stock} ${p.item_name} available.`);
    const existing = lines.find((l) => l.presetId === p.id && !l.bulk);
    if (existing) return patch(existing.key, { qty: String((Number(existing.qty) || 0) + 1) });
    const fresh: Line = { key: `l${++lineSeq}`, presetId: p.id, name: p.item_name, price: String(p.price), qty: "1", bulk: false };
    setLines((ls) => [...ls.filter((l) => l.presetId || l.name.trim() || l.price), fresh]);
  }

  function toggleBulk(l: Line, bulk: boolean) {
    const p = product(l.presetId);
    if (!p) return;
    const next = { ...l, bulk, qty: "1", price: String(bulk ? p.bulk_price : p.price) };
    const probe = { ...next };
    const free = p.track_stock ? p.stock - unitsUsed(p.id, l.key) : Infinity;
    const need = bulk && p.bulk_quantity ? p.bulk_quantity : 1;
    if (free < need) {
      window.alert(bulk ? `Not enough ${p.item_name} in stock for a bulk of ${p.bulk_quantity}.` : `No more ${p.item_name} available.`);
      return;
    }
    patch(l.key, probe);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const items = lines.filter((l) => l.presetId || l.name.trim() || l.price);
    if (items.length === 0) return setError("Add at least one item to the sale.");
    for (const l of items) {
      const q = Number(l.qty), price = Number(l.price.replace(/,/g, ""));
      if (!l.presetId && !l.name.trim()) return setError("Give each custom item a name.");
      if (!Number.isInteger(q) || q < 1) return setError("Quantities must be whole numbers, 1 or more.");
      if (!(price > 0)) return setError("Every item needs a price greater than zero.");
      if (q > limit(l) + 0) return setError(`Only ${limit(l)} available for ${l.name}.`);
    }
    if (paidValue < 0 || paidValue > total + 0.005) return setError("Amount paid cannot be more than the total.");
    setBusy(true);
    setError("");
    try {
      const customerName = customer.trim() || "Walk-in Customer";
      const date = nowStamp();
      const receiptId = `REC-${checkoutId.slice(0, 12).toUpperCase()}`;
      let remaining = paidValue;
      const stock: Record<number, number> = {};
      const rows: Sale[] = items.map((l, i) => {
        const p = product(l.presetId);
        const q = Number(l.qty), price = Number(l.price.replace(/,/g, ""));
        const units = l.bulk && p?.bulk_quantity ? q * p.bulk_quantity : q;
        const lineTotal = price * q;
        const linePaid = Math.min(remaining, lineTotal);
        remaining -= linePaid;
        if (p && p.track_stock) stock[p.id] = (stock[p.id] ?? 0) + units;
        return {
          id: nextTempId(), description: l.presetId ? l.name : l.name.trim(), total_value: lineTotal, amount_paid: linePaid,
          balance_owed: lineTotal - linePaid, customer_name: customerName, payment_mode: mode, date, receipt_id: receiptId,
          checkout_id: checkoutId, checkout_line_id: `line-${i + 1}`, inventory_item_id: l.presetId, quantity: units,
          unit_price: lineTotal / units, sale_type: l.bulk ? "bulk" : "unit", bundle_count: l.bulk ? q : null,
          bundle_size: l.bulk && p?.bulk_quantity ? p.bulk_quantity : null, pending: true,
        };
      });
      await write({
        kind: "checkout", method: "POST", url: "/api/checkout",
        body: {
          checkout_id: checkoutId, customer_name: customerName, payment_mode: mode, amount_paid: paidValue,
          items: items.map((l, i) => ({
            checkout_line_id: `line-${i + 1}`, inventory_item_id: l.presetId, item_name: l.presetId ? undefined : l.name.trim(),
            quantity: Number(l.qty), unit_price: Number(l.price.replace(/,/g, "")), sale_type: l.bulk ? "bulk" : "unit",
          })),
        },
        meta: { sales: rows, stock },
      });
      props.onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the sale. Try again.");
      setBusy(false);
    }
  }

  return (
    <div id="sale-entry-card" className="sb-sheet">
      <div className="sb-sheet-head">
        <h3 id="sale-modal-title" className="sb-sheet-title">New sale</h3>
        <button type="button" data-close-entry="sale-entry-modal" className="sb-icon-btn" aria-label="Close" onClick={props.onClose}>
          <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>
      <form onSubmit={submit} className="sb-sheet-body" noValidate>
        <div className="sb-field">
          <label htmlFor="sales-inventory-select">Add a product</label>
          <select id="sales-inventory-select" value="" onChange={(e) => e.target.value && addProduct(Number(e.target.value))}>
            <option value="">Choose a product</option>
            {products.map((p) => {
              const left = p.track_stock ? Math.max(0, p.stock - unitsUsed(p.id)) : null;
              return (
                <option key={p.id} value={p.id} disabled={left === 0}>
                  {p.item_name} · {money(p.price)}{p.bulk_quantity && p.bulk_price ? ` · bulk ${p.bulk_quantity} for ${money(p.bulk_price)}` : ""}{left === null ? "" : ` · ${left} left`}
                </option>
              );
            })}
          </select>
          <p className="sb-help">
            {products.length ? "Choose a product to add it to the sale. Set the quantity in its line below." : "No products yet. Add products on the Inventory page, or enter a custom item below."}
          </p>
        </div>

        <div className="sale-items-head">
          <span>Items</span>
          <button type="button" className="sb-link" onClick={() => lines.length < 50 && setLines([...lines, blankLine()])}>+ Item not in inventory</button>
        </div>
        <div className="sale-lines-edit">
          {lines.map((l) => {
            const p = product(l.presetId);
            return (
              <div key={l.key} className={`sale-line ${p ? "sale-line-inventory" : ""}`}>
                <label className="sale-line-name"><span>Product</span>
                  <input type="text" maxLength={120} placeholder="Item name" value={l.name} readOnly={Boolean(p)}
                    onChange={(e) => patch(l.key, { name: e.target.value })} aria-label={p ? `Inventory product: ${p.item_name}` : undefined} />
                </label>
                <label><span>{l.bulk ? "Bulk price (₦)" : "Unit price (₦)"}</span>
                  <input type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="0" value={l.price} readOnly={Boolean(p)}
                    onChange={(e) => patch(l.key, { price: e.target.value })} />
                </label>
                <label><span>{l.bulk && p ? `Bulks of ${p.bulk_quantity}` : "Quantity"}</span>
                  <input type="number" inputMode="numeric" min="1" max={Math.max(limit(l), 1)} step="1" value={l.qty}
                    onChange={(e) => patch(l.key, { qty: e.target.value })} />
                </label>
                <button type="button" className="sale-line-remove" aria-label="Remove item"
                  onClick={() => setLines((ls) => (ls.length > 1 ? ls.filter((x) => x.key !== l.key) : [blankLine()]))}>
                  <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M6 6l12 12M18 6 6 18" /></svg>
                </button>
                {p && p.bulk_quantity && p.bulk_price && (
                  <label className="sale-line-bulk" style={{ gridColumn: "1 / -1" }}>
                    <input type="checkbox" className="w-4 h-4 accent-blue-700" checked={l.bulk} onChange={(e) => toggleBulk(l, e.target.checked)} />
                    <span>Sell as bulk ({p.bulk_quantity} for {money(p.bulk_price)})</span>
                  </label>
                )}
                {p && (
                  <span className="sale-line-source" style={{ gridColumn: "1 / -1" }}>
                    {l.bulk ? `Bulk sale · each bulk takes ${p.bulk_quantity} from stock` : "Inventory item · unit price synced"}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        <div className="sb-field">
          <label htmlFor="income-customer-name">Customer <span className="sb-optional">(optional)</span></label>
          <input id="income-customer-name" type="text" placeholder="Walk-in customer" autoComplete="off" value={customer} onChange={(e) => setCustomer(e.target.value)} />
        </div>
        <div className="sb-field-row">
          <div className="sb-field">
            <label htmlFor="income-total-value">Total</label>
            <div className="sb-money"><span aria-hidden="true">₦</span><input id="income-total-value" className="currency-input" readOnly value={total ? total.toLocaleString("en-NG") : ""} placeholder="0" /></div>
          </div>
          <div className="sb-field">
            <label htmlFor="income-amount-paid">Amount paid</label>
            <div className="sb-money"><span aria-hidden="true">₦</span>
              <input id="income-amount-paid" className="currency-input" inputMode="decimal" placeholder="0"
                value={paid === null ? (total ? String(total) : "") : paid} onChange={(e) => setPaid(e.target.value)} />
            </div>
          </div>
        </div>
        <div className="sb-field">
          <label htmlFor="sale-payment-mode">Payment method</label>
          <select id="sale-payment-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option>Cash</option><option>Transfer</option><option>POS</option>
          </select>
        </div>
        {error && <p className="sb-error" role="alert">{error}</p>}
        <div className="sb-sheet-foot">
          <button type="submit" className="sb-btn sb-btn-primary sb-btn-block" disabled={busy}>{busy ? "Saving…" : "Record sale"}</button>
        </div>
      </form>
    </div>
  );
}

function SettleDebt(props: { receipt: Receipt; onClose: () => void }) {
  const { receipt } = props;
  const { write } = useData();
  const line = receipt.items.find((s) => s.total_value - s.amount_paid > 0.005)!;
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const n = Number(amount.replace(/,/g, "")) || 0;
  const after = Math.max(receipt.owed - n, 0);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!(n > 0)) return setError("Enter a payment greater than zero.");
    if (n > receipt.owed + 0.005) return setError("That is more than the balance owed.");
    setBusy(true);
    try {
      // A receipt's balance is cleared line by line, oldest first.
      let left = n;
      for (const s of receipt.items) {
        const owing = s.total_value - s.amount_paid;
        if (owing <= 0.005 || left <= 0) continue;
        const part = Math.min(owing, left);
        await write({ kind: "payment", method: "POST", url: `/update_payment/${s.id}`, body: { payment_amount: part },
          meta: { saleId: s.id, amount: part } });
        left -= part;
      }
      props.onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the payment.");
      setBusy(false);
    }
  }

  return (
    <Sheet title="Settle customer debt" onClose={props.onClose} compact
      description={<p className="sb-sheet-sub">{line.customer_name} · #{line.receipt_id}</p>}>
      <form onSubmit={submit} className="sb-sheet-body">
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="rounded-2xl border border-slate-100 bg-slate-50 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Outstanding</p>
            <p className="mt-1 text-lg font-black text-amber-600">{money(receipt.owed)}</p>
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600">After payment</p>
            <p className="mt-1 text-lg font-black text-emerald-700">{money(after)}</p>
          </div>
        </div>
        <div className="sb-field">
          <label htmlFor="settle-debt-amount">Payment received</label>
          <div className="sb-money"><span aria-hidden="true">₦</span>
            <input id="settle-debt-amount" inputMode="decimal" autoComplete="off" required placeholder="0.00" value={amount}
              onChange={(e) => setAmount(e.target.value)} autoFocus /></div>
          <div className="mt-2 flex gap-2">
            <button type="button" className="sb-chip" onClick={() => setAmount(String(Math.round((receipt.owed / 2) * 100) / 100))}>Half</button>
            <button type="button" className="sb-chip" onClick={() => setAmount(String(receipt.owed))}>Full balance</button>
          </div>
        </div>
        {error && <p className="sb-error" role="alert">{error}</p>}
        <div className="sb-sheet-foot">
          <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose}>Cancel</button>
          <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>Record payment</button>
        </div>
      </form>
    </Sheet>
  );
}

export default function Sales() {
  const { sales, products, profile, write } = useData();
  const [quick, setQuick] = useState<Quick>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [product, setProduct] = useState("");
  const [payment, setPayment] = useState("");
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");
  const [creating, setCreating] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const [settling, setSettling] = useState<Receipt | null>(null);
  const [deleting, setDeleting] = useState<Receipt | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [needProfile, setNeedProfile] = useState(false);

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
  const activeFilters = [product, payment, min, max].filter((v) => v !== "").length;
  const filtered = quick !== "all" || activeFilters > 0;

  async function confirmDelete() {
    if (!deleting) return;
    try {
      const stock: Record<number, number> = {};
      for (const s of deleting.items) {
        if (s.inventory_item_id != null) stock[s.inventory_item_id] = (stock[s.inventory_item_id] ?? 0) + s.quantity;
      }
      await write({ kind: "sale_delete", method: "DELETE", url: `/api/income/${deleting.items[0].id}`,
        meta: { saleIds: deleting.items.map((s) => s.id), checkoutId: deleting.items[0].checkout_id, stock } });
      setDeleting(null);
      setDeleteError("");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Could not delete this sale. Try again.");
    }
  }

  const chips: [Quick, string][] = [["all", "All"], ["today", "Today"], ["week", "This week"], ["bulk", "Bulk sales"]];

  return (
    <section id="tab-income-content" className="tab-content page-stack" aria-labelledby="sales-title">
      <div className="page-head">
        <div className="min-w-0"><h2 className="page-title" id="sales-title">Sales</h2><p className="page-sub">Record every sale, unit or bulk.</p></div>
        <button type="button" id="btn-new-sale" className="sb-btn sb-btn-primary" onClick={() => setCreating(true)}>
          <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path d="M12 5v14M5 12h14" /></svg>
          New sale
        </button>
      </div>

      <div id="sales-main-view" className="page-stack">
        {/* A side panel on desktop; a full-screen sheet on phones. */}
        <div id="sale-entry-modal" className={creating ? "sb-modal" : "sb-modal hidden"} role="dialog" aria-modal="true" aria-labelledby="sale-modal-title">
          <NewSale key={formKey} products={products} onClose={() => setCreating(false)}
            onDone={() => { setCreating(false); setFormKey((k) => k + 1); }} />
        </div>
        <div id="sales-quick-filters" className="flex flex-wrap gap-2" role="group" aria-label="Quick filters">
          {chips.map(([id, label]) => (
            <button key={id} type="button" aria-pressed={quick === id} onClick={() => setQuick(id)}
              className={`sales-quick-chip ${quick === id ? "is-active" : ""}`}>{label}</button>
          ))}
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
        </div>

        {filterOpen && (
          <section id="sales-filter-panel" className="sb-panel filter-panel is-open" aria-label="Filter sales">
            <div className="filter-grid">
              <div className="sb-field"><label htmlFor="sales-product-filter">Product</label>
                <select id="sales-product-filter" value={product} onChange={(e) => setProduct(e.target.value)}>
                  <option value="">All products</option>{names.map((n) => <option key={n}>{n}</option>)}
                </select></div>
              <div className="sb-field"><label htmlFor="sales-payment-filter">Payment</label>
                <select id="sales-payment-filter" value={payment} onChange={(e) => setPayment(e.target.value)}>
                  <option value="">Any</option><option value="paid">Paid in full</option><option value="partial">Part-paid</option><option value="unpaid">Unpaid</option>
                </select></div>
              <div className="sb-field"><label htmlFor="sales-min-total">Sale total from (₦)</label>
                <input id="sales-min-total" type="number" min={0} step="0.01" inputMode="decimal" placeholder="Any" value={min} onChange={(e) => setMin(e.target.value)} /></div>
              <div className="sb-field"><label htmlFor="sales-max-total">Sale total up to (₦)</label>
                <input id="sales-max-total" type="number" min={0} step="0.01" inputMode="decimal" placeholder="Any" value={max} onChange={(e) => setMax(e.target.value)} /></div>
            </div>
          </section>
        )}

        <div id="income-list" className="sale-list" aria-live="polite">
          {receipts.length === 0 && (
            <p className="list-empty">{sales.length === 0 ? "No sales yet. Tap “New sale” to record one." : "No sales match these filters."}</p>
          )}
          {receipts.map((r) => {
            const first = r.items[0];
            const meta = [saleDate(first.date), first.payment_mode || "Cash", first.receipt_id ? `#${first.receipt_id}` : ""].filter(Boolean).join(" · ");
            return (
              <article key={r.key} className="sale-card">
                <div className="sale-card-top">
                  <div className="min-w-0">
                    <p className="sale-customer">{first.customer_name || "Walk-in customer"}{r.items.some((x) => x.pending) && <span className="sale-offline"> Not synced</span>}</p>
                    <p className="sale-meta">{meta}</p>
                  </div>
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
                    onClick={() => (profile?.company_name ? printReceipt(r, profile) : setNeedProfile(true))}>Receipt</button>
                  <button type="button" className="btn-delete-income sb-btn sb-btn-small sb-btn-danger-text" aria-label="Delete this sale"
                    onClick={() => { setDeleting(r); setDeleteError(""); }}>Delete</button>
                </div>
              </article>
            );
          })}
        </div>
        <button type="button" className="sb-btn sb-btn-primary sb-btn-block lg:hidden" onClick={() => setCreating(true)}>+ New sale</button>
      </div>

      {settling && <SettleDebt receipt={settling} onClose={() => setSettling(null)} />}
      {deleting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm" role="alertdialog" aria-modal="true">
          <div className="w-full max-w-sm rounded-3xl border border-slate-100 bg-white p-6 shadow-2xl">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-rose-600">Confirm deletion</p>
            <h3 className="mt-1 text-xl font-black text-slate-900">Delete this sale?</h3>
            <p className="mt-2 text-sm text-slate-600">This will permanently remove the recorded sale. Stock sold in it is returned to inventory.</p>
            {deleteError && <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700" role="alert">{deleteError}</p>}
            <div className="mt-6 flex gap-3">
              <button type="button" className="flex-1 rounded-xl bg-slate-100 py-3 text-xs font-black text-slate-700 hover:bg-slate-200" onClick={() => setDeleting(null)}>Keep sale</button>
              <button type="button" className="flex-1 rounded-xl bg-rose-600 py-3 text-xs font-black text-white shadow-md hover:bg-rose-700" onClick={confirmDelete}>Delete sale</button>
            </div>
          </div>
        </div>
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
