"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDateTime } from "../../lib/api";

type Notif = { id: number; kind: string; body: string; read: boolean; created_at: string | null };

export default function NotificationsPage() {
  const [items, setItems] = useState<Notif[]>([]);
  const [note, setNote] = useState("");

  async function load() {
    const d = await apiFetch("/notifications");
    setItems(d.notifications);
  }
  useEffect(() => { load().catch((e) => setNote(e.message)); }, []);

  async function markRead(n: Notif) {
    if (n.read) return;
    try { await apiFetch(`/notifications/${n.id}/read`, { method: "POST" }); await load(); }
    catch (err) { setNote(err instanceof Error ? err.message : "Update failed"); }
  }
  async function markAll() {
    try { await apiFetch("/notifications/read-all", { method: "POST" }); await load(); }
    catch (err) { setNote(err instanceof Error ? err.message : "Update failed"); }
  }

  const unread = items.filter((n) => !n.read).length;

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">Workspace</span><h1 style={{ margin: "6px 0" }}>Notifications</h1></div>
        {unread > 0 && <button className="btn alt" type="button" onClick={markAll}>Mark all read ({unread})</button>}
      </div>
      <p className="muted">Assignment events and reminders from your workspace.</p>
      {note && <p className="alert" role="status">{note}</p>}
      <div className="panel" style={{ margin: 0 }}>
        {items.map((n) => (
          <div className="ev" key={n.id} style={n.read ? { opacity: 0.55 } : undefined}>
            <span className="tag">{n.kind}</span> {n.body}
            <small>{fmtDateTime(n.created_at)}</small>
            {!n.read && <button className="btn alt mini" type="button" style={{ marginLeft: 8 }} onClick={() => markRead(n)}>Mark read</button>}
          </div>
        ))}
        {!items.length && <p className="muted">Nothing yet. Notifications appear when a teammate assigns you a task or deal, or when your tasks go overdue.</p>}
      </div>
    </>
  );
}
