import { useState, type FormEvent } from "react";
import { ApiError } from "../api";
import Sheet from "./Sheet";
import { useData } from "../data";
import { money } from "../format";
import { nextTempId, nowStamp } from "../offline";
import type { Product, Sale } from "../types";

export type Status = "paid" | "partial" | "unpaid";

export interface Receipt { key: string; items: Sale[]; total: number; paid: number; owed: number; status: Status }


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

export function NewSale(props: { products: Product[]; onClose: () => void; onDone: () => void }) {
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

export function SettleDebt(props: { receipt: Receipt; onClose: () => void }) {
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

