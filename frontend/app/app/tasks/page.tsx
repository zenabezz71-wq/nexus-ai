"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDateTime } from "../../lib/api";

type Task = {
  id: number; title: string; description: string; status: string; priority: string;
  due_at: string | null; completed_at: string | null;
  contact_id: number | null; deal_id: number | null;
};
type Contact = { id: number; name: string };

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [filter, setFilter] = useState<"open" | "done" | "all">("open");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", priority: "normal", due_at: "", contact_id: "" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    const qs = filter === "all" ? "" : `?status=${filter === "open" ? "open" : "done"}`;
    const [ts, cs] = await Promise.all([apiFetch("/tasks" + qs), apiFetch("/contacts")]);
    setTasks(ts); setContacts(cs);
  }
  useEffect(() => { load().catch((e) => setNote(e.message)); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filter]);

  const contactName = (id: number | null) => (id == null ? "" : contacts.find((c) => c.id === id)?.name || "");

  async function submitCreate(e: React.FormEvent) {
    e.preventDefault(); setNote("");
    try {
      await apiFetch("/tasks", {
        method: "POST",
        body: JSON.stringify({
          title: form.title, description: form.description, priority: form.priority,
          due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
          contact_id: form.contact_id ? Number(form.contact_id) : null,
        }),
      });
      setForm({ title: "", description: "", priority: "normal", due_at: "", contact_id: "" });
      setCreating(false); await load();
    } catch (err) { setNote(err instanceof Error ? err.message : "Save failed"); }
  }
  async function setStatus(t: Task, status: string) {
    setBusy(t.id);
    try { await apiFetch(`/tasks/${t.id}`, { method: "PATCH", body: JSON.stringify({ status }) }); await load(); }
    catch (err) { setNote(err instanceof Error ? err.message : "Update failed"); }
    finally { setBusy(null); }
  }
  async function doDelete(t: Task) {
    setBusy(t.id);
    try { await apiFetch(`/tasks/${t.id}`, { method: "DELETE" }); await load(); }
    catch (err) { setNote(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(null); }
  }

  const overdue = (t: Task) => t.status !== "done" && t.due_at && new Date(t.due_at).getTime() < Date.now();

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">CRM</span><h1 style={{ margin: "6px 0" }}>Tasks</h1></div>
        <button className="btn" type="button" onClick={() => setCreating(!creating)}>{creating ? "Close" : "New task"}</button>
      </div>
      {note && <p className="alert" role="status">{note}</p>}
      {creating && (
        <form className="panel" onSubmit={submitCreate}>
          <h3 style={{ marginTop: 0 }}>New task</h3>
          <div className="crm-grid">
            <label>Title *<input required maxLength={300} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
            <label>Due<input type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} /></label>
            <label>Priority
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
              </select>
            </label>
            <label>Contact
              <select value={form.contact_id} onChange={(e) => setForm({ ...form, contact_id: e.target.value })}>
                <option value="">None</option>
                {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label style={{ gridColumn: "1/-1" }}>Description<textarea rows={2} maxLength={10000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          </div>
          <div className="row" style={{ marginTop: 12 }}><button className="btn" type="submit">Create task</button></div>
        </form>
      )}
      <div className="row" style={{ margin: "10px 0" }}>
        {(["open", "done", "all"] as const).map((f) => (
          <button key={f} type="button" className={"btn " + (filter === f ? "" : "alt")} onClick={() => setFilter(f)}>
            {f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <table>
          <thead><tr><th>Task</th><th>Contact</th><th>Priority</th><th>Due</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td>
                  <strong style={{ textDecoration: t.status === "done" ? "line-through" : undefined }}>{t.title}</strong>
                  {t.description && <div className="muted">{t.description}</div>}
                </td>
                <td>{contactName(t.contact_id) || "—"}</td>
                <td>{t.priority !== "normal" ? <span className="tag">{t.priority}</span> : "—"}</td>
                <td style={overdue(t) ? { color: "var(--warn-text)", fontWeight: 700 } : undefined}>
                  {t.status === "done" && t.completed_at ? `Done ${fmtDateTime(t.completed_at)}` : t.due_at ? fmtDateTime(t.due_at) : "—"}
                </td>
                <td><span className="tag">{t.status}</span></td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    {t.status !== "done"
                      ? <button className="btn alt mini" type="button" disabled={busy === t.id} onClick={() => setStatus(t, "done")}>Done</button>
                      : <button className="btn alt mini" type="button" disabled={busy === t.id} onClick={() => setStatus(t, "open")}>Reopen</button>}
                    <button className="btn alt mini" type="button" disabled={busy === t.id} onClick={() => doDelete(t)}>✕</button>
                  </div>
                </td>
              </tr>
            ))}
            {!tasks.length && <tr><td colSpan={6} className="muted">No {filter === "all" ? "" : filter + " "}tasks. Create one to keep follow-ups visible.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
