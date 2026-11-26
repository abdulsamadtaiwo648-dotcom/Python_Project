import { useEffect, useState } from "react";
import { ApiError, api } from "../api";

interface Plan {
  clears: {
    sales: number; sale_payments: number; expenses: number; money_in: number; import_batches: number;
    stock_restored: { product_id: number; item_name: string; quantity: number }[];
    kept: { accounts: number; products: number; expense_categories: number };
  };
  confirm_word: string;
}

/** Test businesses only: clears the test transactions and keeps the setup. The owner must type DELETE. */
export default function TestReset() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setPlan(await api.get<Plan>("/api/test-reset"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not check the test business.");
    }
  }

  useEffect(() => { void load(); }, []);

  async function run() {
    setBusy(true);
    setError("");
    try {
      await api.post("/api/test-reset", { confirm: word });
      setMessage("Test transactions deleted. Your accounts, products and settings are kept.");
      setWord("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The reset did not run. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!plan) return null;
  const c = plan.clears;
  const total = c.sales + c.expenses + c.money_in + c.import_batches;
  return (
    <section className="sb-panel space-y-3 border-rose-200" aria-labelledby="test-reset-title">
      <h3 id="test-reset-title" className="text-base font-bold text-rose-800">Delete all test transactions</h3>
      <p className="text-xs text-slate-600">
        This business is marked as a test business. Reset clears: {c.sales} sales ({c.sale_payments} payments), {c.expenses} expenses,
        {" "}{c.money_in} money in entries, and {c.import_batches} import batches. Stock sold in those sales is put back.
        It keeps your accounts ({c.kept.accounts}), products ({c.kept.products}) and expense categories ({c.kept.expense_categories}).
      </p>
      {c.stock_restored.length > 0 && (
        <p className="text-xs text-slate-600">Stock restored: {c.stock_restored.map((s) => `${s.item_name} +${s.quantity}`).join(", ")}.</p>
      )}
      {message && <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{message}</p>}
      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      <div className="flex flex-wrap items-end gap-2">
        <div className="sb-field">
          <label htmlFor="test-reset-word">Type {plan.confirm_word} to confirm</label>
          <input id="test-reset-word" type="text" autoComplete="off" value={word} onChange={(e) => setWord(e.target.value)} />
        </div>
        <button type="button" className="sb-btn sb-btn-danger" disabled={busy || word !== plan.confirm_word || total === 0}
          onClick={() => void run()}>{busy ? "Deleting…" : "Delete test transactions"}</button>
      </div>
    </section>
  );
}
