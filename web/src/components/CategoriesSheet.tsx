import { useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import type { ExpenseCategory } from "../categories";
import Sheet from "./Sheet";

/** Add, rename and archive the business's expense categories. Changes go straight to the server. */
export default function CategoriesSheet(props: { categories: ExpenseCategory[]; onChanged: () => void; onClose: () => void }) {
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError("");
    try {
      await action();
      after?.();
      props.onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return setError("Enter a category name.");
    void run(() => api.post("/api/expense-categories", { name }), () => setNewName(""));
  }

  function rename(c: ExpenseCategory) {
    const name = draft.trim();
    if (!name) return setError("Enter a category name.");
    void run(() => api.put(`/api/expense-categories/${c.id}`, { name }), () => setEditingId(null));
  }

  return (
    <Sheet title="Expense categories" onClose={props.onClose} description="Archived categories stay on the expenses that used them, but cannot be picked for new ones.">
      <div className="sb-sheet-body">
        {error && <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">{error}</p>}
        <ul className="flex flex-col gap-2" aria-label="Your categories">
          {props.categories.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
              {editingId === c.id ? (
                <>
                  <label className="sr-only" htmlFor={`rename-${c.id}`}>New name for {c.name}</label>
                  <input id={`rename-${c.id}`} className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
                    value={draft} maxLength={80} onChange={(e) => setDraft(e.target.value)} autoFocus />
                  <button type="button" className="sb-btn sb-btn-primary" disabled={busy} onClick={() => rename(c)}>Save</button>
                  <button type="button" className="sb-btn sb-btn-secondary" onClick={() => setEditingId(null)}>Cancel</button>
                </>
              ) : (
                <>
                  <span className={`min-w-0 flex-1 truncate text-sm ${c.archived ? "text-slate-400 line-through" : "text-slate-900"}`}>{c.name}</span>
                  {c.archived && <span className="text-xs text-slate-500">Archived</span>}
                  <button type="button" className="sb-btn sb-btn-secondary" disabled={busy}
                    onClick={() => { setEditingId(c.id); setDraft(c.name); setError(""); }}>Rename</button>
                  <button type="button" className="sb-btn sb-btn-secondary" disabled={busy}
                    onClick={() => void run(() => api.put(`/api/expense-categories/${c.id}`, { archived: !c.archived }))}>
                    {c.archived ? "Restore" : "Archive"}
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        <form onSubmit={add} className="sb-field mt-4">
          <label htmlFor="new-category">Add a category</label>
          <div className="flex gap-2">
            <input id="new-category" type="text" maxLength={80} placeholder="e.g. Generator servicing" value={newName}
              onChange={(e) => setNewName(e.target.value)} className="min-w-0 flex-1" />
            <button type="submit" className="sb-btn sb-btn-primary" disabled={busy}>Add</button>
          </div>
        </form>
      </div>
    </Sheet>
  );
}
