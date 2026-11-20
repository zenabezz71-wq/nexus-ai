"use client";
import { useEffect, useState } from "react";
import { API, apiFetch, fmtDate, fmtDateTime, Me } from "../../lib/api";

type Contact = {
  id: number; name: string; phone: string; email: string; company: string;
  position: string; source: string; priority: string; tags: string[]; notes: string;
  lead_id: number | null; assigned_to: number | null; created_at: string | null;
};
type Deal = { id: number; title: string; amount: number | null; currency: string; status: string; stage_id: number | null };
type Task = { id: number; title: string; status: string; due_at: string | null; priority: string };
type Activity = { id: number; kind: string; body: string; user_id: number; created_at: string | null };
type Profile = Contact & { deals: Deal[]; tasks: Task[]; activities: Activity[] };

const EMPTY = { name: "", phone: "", email: "", company: "", priority: "normal", notes: "" };

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [q, setQ] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [noteKind, setNoteKind] = useState("note");
  const [noteBody, setNoteBody] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(search = q) {
    const rows = await apiFetch("/contacts" + (search.trim() ? `?q=${encodeURIComponent(search.trim())}` : ""));
    setContacts(rows);
  }
  async function open(id: number) {
    setProfile(await apiFetch(`/contacts/${id}`));
    setEditing(false); setConfirmDelete(false);
  }
  useEffect(() => {
    apiFetch("/auth/me").then(setMe).catch(() => {});
    load().catch((e) => setNote(e.message));
    const openId = new URLSearchParams(window.location.search).get("open");
    if (openId) open(Number(openId)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canDelete = me ? (me.permissions ? me.permissions.includes("contacts.view_all") : ["owner", "admin"].includes(me.role)) : false;
  const canExport = me ? (me.permissions ? me.permissions.includes("contacts.export") : ["owner", "admin"].includes(me.role)) : false;

  async function exportCsv() {
    setBusy(true); setNote("");
    try {
      const token = localStorage.getItem("nexus_token") || "";
      const r = await fetch(API + "/contacts/export", { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) throw new Error(`Export failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "nexus-contacts.csv"; a.click();
      URL.revokeObjectURL(url);
      setNote("Contacts exported to CSV.");
    } catch (err) { setNote(err instanceof Error ? err.message : "Export failed"); }
    finally { setBusy(false); }
  }

  async function submitCreate(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setNote("");
    try {
      const c = await apiFetch("/contacts", { method: "POST", body: JSON.stringify(form) });
      setForm(EMPTY); setCreating(false);
      await load(); await open(c.id);
      setNote("Contact saved.");
    } catch (err) { setNote(err instanceof Error ? err.message : "Save failed"); }
    finally { setBusy(false); }
  }
  async function submitEdit(e: React.FormEvent) {
    e.preventDefault(); if (!profile) return; setBusy(true); setNote("");
    try {
      await apiFetch(`/contacts/${profile.id}`, { method: "PATCH", body: JSON.stringify(form) });
      setEditing(false); await load(); await open(profile.id);
      setNote("Contact updated.");
    } catch (err) { setNote(err instanceof Error ? err.message : "Update failed"); }
    finally { setBusy(false); }
  }
  async function addNote(e: React.FormEvent) {
    e.preventDefault(); if (!profile || !noteBody.trim()) return; setBusy(true);
    try {
      await apiFetch("/activities", { method: "POST", body: JSON.stringify({ kind: noteKind, body: noteBody.trim(), contact_id: profile.id }) });
      setNoteBody(""); await open(profile.id);
    } catch (err) { setNote(err instanceof Error ? err.message : "Note failed"); }
    finally { setBusy(false); }
  }
  async function doDelete() {
    if (!profile) return; setBusy(true);
    try {
      await apiFetch(`/contacts/${profile.id}`, { method: "DELETE" });
      setProfile(null); setConfirmDelete(false); await load();
      setNote("Contact archived.");
    } catch (err) { setNote(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  const formFields = (f: typeof EMPTY, set: (v: typeof EMPTY) => void) => (
    <div className="crm-grid">
      <label>Name *<input required maxLength={200} value={f.name} onChange={(e) => set({ ...f, name: e.target.value })} /></label>
      <label>Phone<input maxLength={40} value={f.phone} onChange={(e) => set({ ...f, phone: e.target.value })} /></label>
      <label>Email<input type="email" maxLength={320} value={f.email} onChange={(e) => set({ ...f, email: e.target.value })} /></label>
      <label>Company<input maxLength={200} value={f.company} onChange={(e) => set({ ...f, company: e.target.value })} /></label>
      <label>Priority
        <select value={f.priority} onChange={(e) => set({ ...f, priority: e.target.value })}>
          <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
        </select>
      </label>
      <label style={{ gridColumn: "1/-1" }}>Notes<textarea rows={2} maxLength={10000} value={f.notes} onChange={(e) => set({ ...f, notes: e.target.value })} /></label>
    </div>
  );

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">CRM</span><h1 style={{ margin: "6px 0" }}>Contacts</h1></div>
        <div className="row">
          {canExport && <button className="btn alt" type="button" disabled={busy} onClick={exportCsv}>Export CSV</button>}
          <button className="btn" type="button" onClick={() => { setCreating(!creating); setForm(EMPTY); }}>{creating ? "Close" : "New contact"}</button>
        </div>
      </div>
      {note && <p className="alert" role="status">{note}</p>}
      {creating && (
        <form className="panel" onSubmit={submitCreate}>
          <h3 style={{ marginTop: 0 }}>New contact</h3>
          {formFields(form, setForm)}
          <div className="row" style={{ marginTop: 12 }}><button className="btn" disabled={busy} type="submit">Save contact</button></div>
        </form>
      )}
      <form className="row" style={{ margin: "14px 0" }} onSubmit={(e) => { e.preventDefault(); load().catch((err) => setNote(err.message)); }}>
        <input placeholder="Search name, phone, email or company" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1, minWidth: 200 }} />
        <button className="btn alt" type="submit">Search</button>
        {q && <button className="btn alt" type="button" onClick={() => { setQ(""); load("").catch(() => {}); }}>Clear</button>}
      </form>
      <div style={{ display: "grid", gridTemplateColumns: profile ? "minmax(280px,1fr) minmax(320px,1fr)" : "1fr", gap: 18, alignItems: "start" }}>
        <div className="panel" style={{ margin: 0 }}>
          <table>
            <thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Priority</th><th>Added</th></tr></thead>
            <tbody>
              {contacts.map((c) => (
                <tr key={c.id} onClick={() => open(c.id).catch((e) => setNote(e.message))}
                    style={{ cursor: "pointer", background: profile?.id === c.id ? "var(--surface2)" : undefined }}>
                  <td><strong>{c.name}</strong></td><td>{c.company || "—"}</td><td>{c.phone || "—"}</td>
                  <td>{c.priority !== "normal" ? <span className="tag">{c.priority}</span> : "—"}</td>
                  <td>{fmtDate(c.created_at)}</td>
                </tr>
              ))}
              {!contacts.length && <tr><td colSpan={5} className="muted">No contacts yet. Create one, or convert a lead from the dashboard.</td></tr>}
            </tbody>
          </table>
        </div>
        {profile && (
          <div className="panel" style={{ margin: 0 }}>
            <div className="workspace-heading" style={{ marginBottom: 8 }}>
              <h2 style={{ margin: 0 }}>{profile.name}</h2>
              <div className="row">
                {!editing && <button className="btn alt mini" type="button" onClick={() => { setEditing(true); setForm({ name: profile.name, phone: profile.phone, email: profile.email, company: profile.company, priority: profile.priority, notes: profile.notes }); }}>Edit</button>}
                {canDelete && !confirmDelete && <button className="btn alt mini" type="button" onClick={() => setConfirmDelete(true)}>Archive</button>}
              </div>
            </div>
            {confirmDelete && (
              <div className="alert" style={{ marginBottom: 12 }}>
                Archive {profile.name}? Hidden from lists, data retained. Their deals and tasks stay.
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="btn mini" type="button" disabled={busy} onClick={doDelete}>Confirm archive</button>
                  <button className="btn alt mini" type="button" onClick={() => setConfirmDelete(false)}>Cancel</button>
                </div>
              </div>
            )}
            {editing ? (
              <form onSubmit={submitEdit}>
                {formFields(form, setForm)}
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="btn" disabled={busy} type="submit">Save changes</button>
                  <button className="btn alt" type="button" onClick={() => setEditing(false)}>Cancel</button>
                </div>
              </form>
            ) : (
              <div style={{ display: "grid", gap: 4, fontSize: 14 }}>
                {profile.phone && <div><span className="muted">Phone: </span>{profile.phone}</div>}
                {profile.email && <div><span className="muted">Email: </span>{profile.email}</div>}
                {profile.company && <div><span className="muted">Company: </span>{profile.company}{profile.position ? ` — ${profile.position}` : ""}</div>}
                <div><span className="muted">Source: </span>{profile.source} · <span className="muted">Priority: </span>{profile.priority}</div>
                {profile.notes && <p style={{ lineHeight: 1.7 }}>{profile.notes}</p>}
              </div>
            )}
            {!!profile.deals.length && (
              <><h3>Deals</h3>
              <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                {profile.deals.map((d) => <li key={d.id}>{d.title}{d.amount != null ? ` — ${d.amount} ${d.currency}` : ""} <span className="tag">{d.status}</span></li>)}
              </ul></>
            )}
            {!!profile.tasks.length && (
              <><h3>Tasks</h3>
              <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                {profile.tasks.map((t) => <li key={t.id} style={{ textDecoration: t.status === "done" ? "line-through" : undefined }}>{t.title}{t.due_at ? ` · due ${fmtDate(t.due_at)}` : ""}</li>)}
              </ul></>
            )}
            <h3>Activity</h3>
            <form className="row" onSubmit={addNote} style={{ marginBottom: 10 }}>
              <select value={noteKind} onChange={(e) => setNoteKind(e.target.value)}>
                <option value="note">Note</option><option value="call">Call</option>
                <option value="meeting">Meeting</option><option value="message">Message</option><option value="email">Email</option>
              </select>
              <input required maxLength={10000} placeholder="Log what happened..." value={noteBody} onChange={(e) => setNoteBody(e.target.value)} style={{ flex: 1, minWidth: 160 }} />
              <button className="btn alt" disabled={busy} type="submit">Log</button>
            </form>
            <div className="timeline">
              {profile.activities.map((a) => (
                <div className="ev" key={a.id}><span className="tag">{a.kind}</span> {a.body}<small>{fmtDateTime(a.created_at)}</small></div>
              ))}
              {!profile.activities.length && <p className="muted">No activity yet.</p>}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
