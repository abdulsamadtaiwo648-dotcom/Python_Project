import EmptyState from "../components/EmptyState";
import Skeleton from "../components/Skeleton";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import PushCard from "../components/PushCard";
import { isUpgradeError } from "../components/Upgrade";
import { Link } from "react-router-dom";
import Sheet from "../components/Sheet";
import { useData } from "../data";
import { money } from "../format";
import { useToast } from "../ui/Toast";
import type { Product } from "../types";
import InfoTip from "../components/InfoTip";

const threshold = (p: Product) => (Number.isInteger(p.low_stock_threshold) && p.low_stock_threshold >= 0 ? p.low_stock_threshold : 3);
export function stockLevel(p: Product): "untracked" | "out" | "low" | "ok" {
  if (!p.track_stock) return "untracked";
  const s = Number(p.stock || 0);
  if (s <= 0) return "out";
  return s <= threshold(p) ? "low" : "ok";
}
const bulkOffer = (p: Product) => (p.bulk_quantity && p.bulk_price ? `${p.bulk_quantity} for ${money(p.bulk_price)}` : "");

type Chip = "all" | "low" | "out" | "bulk";

function ProductForm(props: { product?: Product; focusStock?: boolean; onClose: () => void; onSaved: () => Promise<void>; onDelete: (p: Product) => void }) {
  // Whether this product is shown on the public website. Read from the website settings, saved on change.
  const [onSite, setOnSite] = useState<boolean | null>(null);
  const [siteError, setSiteError] = useState("");
  useEffect(() => {
    if (!props.product) return;
    let live = true;
    api.get<{ website: { products: { id: number; show_on_website: boolean }[] } }>("/api/website")
      .then((r) => { if (live) setOnSite(r.website.products.find((x) => x.id === props.product!.id)?.show_on_website ?? null); })
      .catch(() => { if (live) setOnSite(null); });
    return () => { live = false; };
  }, [props.product?.id]);
  async function toggleSite(show: boolean) {
    if (!props.product) return;
    setSiteError("");
    try {
      await api.put(`/api/website/products/${props.product.id}`, { show_on_website: show });
      setOnSite(show);
    } catch (err) {
      setSiteError(err instanceof ApiError ? err.message : "Could not change that. Try again.");
    }
  }
  const p = props.product;
  const adding = !p;
  const [name, setName] = useState(p?.item_name ?? "");
  const [price, setPrice] = useState(p ? String(p.price) : "");
  const [stock, setStock] = useState(p ? String(p.stock) : "0");
  const [low, setLow] = useState(p ? String(threshold(p)) : "3");
  const [bulkQty, setBulkQty] = useState(p?.bulk_quantity ? String(p.bulk_quantity) : "");
  const [bulkPrice, setBulkPrice] = useState(p?.bulk_price ? String(p.bulk_price) : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [upgrade, setUpgrade] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const priceN = Number(price.replace(/,/g, ""));
    const stockN = Number(stock), lowN = Number(low);
    if (!name.trim()) return setError("Enter the product name.");
    if (!Number.isFinite(priceN) || priceN <= 0) return setError("Enter a price greater than zero.");
    if (!Number.isInteger(stockN) || stockN < 0) return setError("Stock must be a whole number, 0 or more.");
    if (!Number.isInteger(lowN) || lowN < 0) return setError("The alert level must be a whole number, 0 or more.");
    let bulk_quantity: number | null = null, bulk_price: number | null = null;
    if (bulkQty.trim() || bulkPrice.trim()) {
      bulk_quantity = Number(bulkQty);
      bulk_price = Number(bulkPrice.replace(/,/g, ""));
      if (!Number.isInteger(bulk_quantity) || bulk_quantity < 2 || !Number.isFinite(bulk_price) || bulk_price <= 0) {
        return setError("For a bulk sale, enter how many pieces make one bulk (2 or more) and the bulk price. Leave both empty to sell by the piece only.");
      }
    }
    setBusy(true);
    setError("");
    try {
      const body = { item_name: name.trim(), price: priceN, stock: stockN, low_stock_threshold: lowN, bulk_quantity, bulk_price };
      if (p) await api.put(`/api/inventory-presets/${p.id}`, body);
      else await api.post("/api/inventory-presets", body);
      await props.onSaved();
      props.onClose();
    } catch (err) {
      setUpgrade(isUpgradeError(err));
      setError(err instanceof ApiError ? err.message : "Could not save. Try again.");
      setBusy(false);
    }
  }

  // Handed to the page, which hides the product and sends the delete after five seconds unless Undo is tapped.
  function remove() {
    if (!p) return;
    props.onDelete(p);
    props.onClose();
  }


  return (
    <Sheet title={adding ? "Add product" : "Edit product"} onClose={props.onClose}
      description={<p className="sb-sheet-sub">{adding ? "Name, price and how many you have." : "Price, stock, bulk price and low-stock alert."}</p>}>
      <form onSubmit={save} className="sb-sheet-body" noValidate>
        <div className="sb-field">
          <label htmlFor="inventory-edit-name">Product name</label>
          <input id="inventory-edit-name" type="text" maxLength={120} required placeholder="e.g. Jogger" value={name}
            onChange={(e) => setName(e.target.value)} autoFocus={!props.focusStock} />
        </div>
        <div className="sb-field-row">
          <div className="sb-field">
            <label htmlFor="inventory-edit-price">Price per piece (₦)</label>
            <input id="inventory-edit-price" type="number" inputMode="decimal" min="0.01" step="0.01" required placeholder="3000" value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
          <div className="sb-field">
            <label htmlFor="inventory-edit-stock">{adding ? "Starting stock" : "Units in stock"}</label>
            <input id="inventory-edit-stock" type="number" inputMode="numeric" min="0" step="1" required value={stock}
              onChange={(e) => setStock(e.target.value)} autoFocus={props.focusStock} onFocus={(e) => props.focusStock && e.target.select()} />
          </div>
        </div>
        <div className="sb-field">
          <label htmlFor="inventory-edit-low-stock">Low-stock alert at</label>
          <input id="inventory-edit-low-stock" type="number" inputMode="numeric" min="0" step="1" required value={low}
            onChange={(e) => setLow(e.target.value)} aria-describedby="low-help" />
          <p id="low-help" className="sb-help"><span>About alert level</span> <InfoTip label="About alert level">You'll be alerted when stock falls to this number or below. Use 0 to be alerted only when it runs out.</InfoTip></p>
        </div>
        <fieldset className="sb-fieldset">
          <legend>Bulk price <span>(optional)</span></legend>
          <div className="sb-field-row">
            <div className="sb-field">
              <label htmlFor="inventory-edit-bulk-quantity">Pieces per bulk</label>
              <input id="inventory-edit-bulk-quantity" type="number" inputMode="numeric" min="2" step="1" placeholder="e.g. 5" value={bulkQty} onChange={(e) => setBulkQty(e.target.value)} />
            </div>
            <div className="sb-field">
              <label htmlFor="inventory-edit-bulk-price">Bulk price (₦)</label>
              <input id="inventory-edit-bulk-price" type="number" inputMode="decimal" min="0.01" step="0.01" placeholder="e.g. 10000" value={bulkPrice} onChange={(e) => setBulkPrice(e.target.value)} />
            </div>
          </div>
          <p className="sb-help"><span>About bulk price</span> <InfoTip label="About bulk price">Only used when you tick "Sell as bulk" on a sale. Leave both empty to sell by the piece only.</InfoTip></p>
        </fieldset>
        {error && <p className="sb-error" role="alert">{error}{upgrade && <> <Link to="/plans" className="font-semibold underline">See plans</Link></>}</p>}
        {props.product && onSite !== null && (
          <div className="sb-field" style={{ marginTop: 8 }}>
            <label className="wb-switch" style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44 }}>
              <input type="checkbox" checked={onSite} onChange={(e) => void toggleSite(e.target.checked)} />
              <span>Show on my website</span>
            </label>
            {siteError && <p className="sb-error" role="alert">{siteError}</p>}
          </div>
        )}
        <div className="sb-sheet-foot">
          {!adding && <button type="button" className="sb-btn sb-btn-danger-text" onClick={remove}>Delete</button>}
          <button type="button" className="sb-btn sb-btn-secondary" onClick={props.onClose}>Cancel</button>
          <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>{adding ? "Add product" : "Save changes"}</button>
        </div>
      </form>
    </Sheet>
  );
}

export default function Inventory() {
  const { products: allProducts, reload, loading } = useData();
  // Products deleted but not yet confirmed. Hidden now; the delete is sent after five seconds unless Undo is tapped.
  const [hidden, setHidden] = useState<Set<number>>(() => new Set());
  const products = useMemo(() => allProducts.filter((p) => !hidden.has(p.id)), [allProducts, hidden]);
  const toast = useToast();
  const [chip, setChip] = useState<Chip>("all");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"cards" | "table">("cards");
  const [editing, setEditing] = useState<{ product?: Product; restock?: boolean } | null>(null);
  function scheduleDelete(p: Product) {
    setHidden((h) => new Set(h).add(p.id));
    const unhide = () => setHidden((h) => { const n = new Set(h); n.delete(p.id); return n; });
    const timer = window.setTimeout(() => {
      api.del(`/api/inventory-presets/${p.id}`)
        .then(() => reload())
        .catch(() => { unhide(); toast({ text: "Could not delete that product. It is back in your list." }); });
    }, 5000);
    toast({ text: `${p.item_name} deleted.`, actionLabel: "Undo", onAction: () => { window.clearTimeout(timer); unhide(); } });
  }

  useEffect(() => { document.title = "Inventory | SoloBiz"; }, []);

  const counts = useMemo(() => ({
    all: products.length,
    low: products.filter((p) => stockLevel(p) === "low").length,
    out: products.filter((p) => stockLevel(p) === "out").length,
  }), [products]);
  const needing = products.filter((p) => stockLevel(p) === "low" || stockLevel(p) === "out").sort((a, b) => a.stock - b.stock);

  const rows = products.filter((p) => {
    const level = stockLevel(p);
    if (chip === "low" && level !== "low") return false;
    if (chip === "out" && level !== "out") return false;
    if (chip === "bulk" && !bulkOffer(p)) return false;
    return !query.trim() || p.item_name.toLowerCase().includes(query.trim().toLowerCase());
  });

  const chips: [Chip, string][] = [["all", "All"], ["low", "Low stock"], ["out", "Out of stock"], ["bulk", "Bulk offers"]];

  return (
    <section id="tab-inventory-content" className="tab-content page-stack" aria-labelledby="inventory-title">
      <div className="page-head">
        <div className="min-w-0"><h2 className="page-title" id="inventory-title">Inventory</h2><p className="page-sub">Stock levels, prices and bulk offers.</p></div>
        <button type="button" id="btn-manage-presets" className="sb-btn sb-btn-primary" onClick={() => setEditing({})}>
          <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}><path d="M12 5v14M5 12h14" /></svg>
          Add product
        </button>
      </div>

      <div id="inv-chips" className="flex flex-wrap gap-2" role="group" aria-label="Filter products">
        {chips.map(([id, label]) => (
          <button key={id} type="button" aria-pressed={chip === id} onClick={() => setChip(id)}
            className={`sales-quick-chip ${chip === id ? "is-active" : ""}`}>{label}</button>
        ))}
      </div>
      <label className="sb-search">
        <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input type="search" className="inventory-search" placeholder="Search products" aria-label="Search inventory products" value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>

      {needing.length > 0 && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4" role="alert" aria-live="polite">
          <div className="flex items-start gap-3">
            <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-rose-600" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
            </svg>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-rose-900">
                {needing.length} product{needing.length === 1 ? " needs" : "s need"} restocking: {[
                  counts.out ? `${counts.out} out of stock` : "", counts.low ? `${counts.low} running low` : ""].filter(Boolean).join(", ")}
              </p>
              <p className="mt-0.5 text-xs text-rose-800">Restock these products so you don't miss sales. Change a product's alert level from Edit.</p>
              <ul className="mt-3 space-y-2">
                {needing.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 rounded-xl border border-rose-100 bg-white/80 px-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">{p.item_name}</p>
                      <p className={`text-xs ${stockLevel(p) === "out" ? "font-semibold text-rose-700" : "text-amber-700"}`}>
                        {stockLevel(p) === "out" ? "Out of stock" : `${p.stock} left · alert at ${threshold(p)}`}
                      </p>
                    </div>
                    <button type="button" aria-label={`Restock ${p.item_name}`} onClick={() => setEditing({ product: p, restock: true })}
                      className="flex-shrink-0 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-rose-700">Restock</button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <PushCard />

      <div id="inv-summary" className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Products</p>
          <p className="stat-value mt-1 text-2xl text-slate-900">{counts.all}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Low stock</p>
          <p className="stat-value mt-1 text-2xl text-amber-700">{counts.low}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Out of stock</p>
          <p className="stat-value mt-1 text-2xl text-rose-700">{counts.out}</p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-500">Showing your products</p>
        <div className="inline-flex rounded-xl bg-slate-100 p-1" role="group" aria-label="Choose how to view products">
          {(["cards", "table"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
              className={`inv-view-btn ${view === v ? "is-active" : ""}`}>{v === "cards" ? "Cards" : "Table"}</button>
          ))}
        </div>
      </div>

      {view === "cards" ? (
        <div className="ui-product-grid" aria-label="Products">
          {loading && products.length === 0 && <Skeleton rows={3} label="Loading stock" />}
          {!loading && products.length === 0 && <EmptyState message="No products yet. Add the things you sell to track stock." action={<button type="button" className="sb-btn sb-btn-primary" onClick={() => setEditing({})}>Add a product</button>} />}
          {products.length > 0 && rows.length === 0 && <p className="text-center text-slate-500">No products match.</p>}
          {rows.map((p) => {
            const level = stockLevel(p);
            const badge = level === "out" ? { text: "Sold out", cls: "is-sold" } : level === "low" ? { text: "Low stock", cls: "is-low" } : level === "ok" ? { text: "In stock", cls: "is-ok" } : null;
            return (
              <button key={p.id} type="button" className="ui-product-card" aria-label={`Edit ${p.item_name}`} onClick={() => setEditing({ product: p })}>
                <span className="ui-product-photo" aria-hidden="true">{p.item_name.trim().charAt(0).toUpperCase() || "?"}</span>
                <span className="ui-product-name">{p.item_name}</span>
                <span className="ui-product-price">{money(p.price)}</span>
                <span className="ui-product-stock">{level === "untracked" ? "Not tracked" : `${p.stock} in stock`}</span>
                {badge && <span className={`ui-product-badge ${badge.cls}`}>{badge.text}</span>}
              </button>
            );
          })}
        </div>
      ) : (
      <div className={`sb-list-card ${view === "table" ? "inv-view-table" : ""}`} id="inv-list-card">
        <div className="inventory-table-wrap">
          <table>
            <thead><tr><th>Product</th><th>Status</th><th>Stock</th><th>Price</th></tr></thead>
            <tbody id="presets-grid">
              {loading && products.length === 0 && <tr><td colSpan={4} className="py-6"><Skeleton rows={3} label="Loading stock" /></td></tr>}
              {!loading && products.length === 0 && <tr><td colSpan={4} className="py-6"><EmptyState message="No products yet. Add the things you sell to track stock." action={<button type="button" className="sb-btn sb-btn-primary" onClick={() => setEditing({})}>Add a product</button>} /></td></tr>}
              {products.length > 0 && rows.length === 0 && <tr><td colSpan={4} className="py-8 text-center text-slate-500">No products match.</td></tr>}
              {rows.map((p) => {
                const level = stockLevel(p);
                return (
                  <tr key={p.id} tabIndex={0} aria-label={`Edit ${p.item_name}`} onClick={() => setEditing({ product: p })}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setEditing({ product: p })}>
                    <td className="font-semibold">{p.item_name}</td>
                    <td><span className={`inventory-status ${level === "out" ? "out" : level === "low" ? "low" : ""}`}>
                      {level === "out" ? "Out of stock" : level === "low" ? "Low stock" : "In stock"}</span></td>
                    <td>{level === "untracked" ? "Not tracked" : <>{p.stock} in stock<span className="block text-[10px] text-slate-500">Alert at {threshold(p)}</span></>}</td>
                    <td className="font-semibold">{money(p.price)}{bulkOffer(p) && <span className="block text-[10px] font-semibold text-blue-700">Bulk: {bulkOffer(p)}</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      )}
      <p className="page-note">Tap a product to edit its price, stock, bulk price or low-stock alert.</p>

      {editing && <ProductForm product={editing.product} focusStock={editing.restock} onClose={() => setEditing(null)} onSaved={reload} onDelete={scheduleDelete} />}
    </section>
  );
}
