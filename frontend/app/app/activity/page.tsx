"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDateTime } from "../../lib/api";

type Activity = {
  id: number; kind: string; body: string; user_id: number;
  contact_id: number | null; deal_id: number | null; lead_id: number | null;
  created_at: string | null;
};
type Contact = { id: number; name: string };
type Deal = { id: number; title: string };

const FILTERS: { key: string; label: string; match: (k: string) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "logged", label: "Notes & comms", match: (k) => ["note", "call", "meeting", "message", "email"].includes(k) },
  { key: "deals", label: "Deals", match: (k) => k.startsWith("deal.") },
  { key: "contacts", label: "Contacts & leads", match: (k) => k.startsWith("contact.") || k.startsWith("lead.") },
  { key: "tasks", label: "Tasks", match: (k) => k.startsWith("task.") },
  { key: "pipeline", label: "Pipeline", match: (k) => k.startsWith("pipeline.") },
];

export default function ActivityPage() {
  const [acts, setActs] = useState<Activity[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [filter, setFilter] = useState("all");
  const [note, setNote] = useState("");

  useEffect(() => {
    Promise.all([apiFetch("/activities?limit=300"), apiFetch("/contacts"), apiFetch("/deals")])
      .then(([a, c, d]) => { setActs(a); setContacts(c); setDeals(d); })
      .catch((e) => setNote(e.message));
  }, []);

  const contactName = (id: number | null) => (id == null ? "" : contacts.find((c) => c.id === id)?.name || "");
  const dealTitle = (id: number | null) => (id == null ? "" : deals.find((d) => d.id === id)?.title || "");
  const shown = acts.filter((a) => (FILTERS.find((f) => f.key === filter) || FILTERS[0]).match(a.kind));

  // group by calendar day
  const days: { day: string; items: Activity[] }[] = [];
  for (const a of shown) {
    const day = a.created_at ? new Date(a.created_at).toDateString() : "Earlier";
    const last = days[days.length - 1];
    if (last && last.day === day) last.items.push(a);
    else days.push({ day, items: [a] });
  }

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">CRM</span><h1 style={{ margin: "6px 0" }}>Activity</h1></div>
      </div>
      <p className="muted">Everything recorded across contacts, deals, tasks and the pipeline.</p>
      {note && <p className="alert" role="status">{note}</p>}
      <div className="row" style={{ margin: "10px 0" }}>
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className={"btn " + (filter === f.key ? "" : "alt")} onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
      </div>
      <div className="panel" style={{ margin: 0 }}>
        {days.map((g) => (
          <div key={g.day} style={{ marginBottom: 18 }}>
            <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>{g.day}</h3>
            <div className="timeline">
              {g.items.map((a) => (
                <div className="ev" key={a.id}>
                  <span className="tag">{a.kind}</span> {a.body}
                  {(contactName(a.contact_id) || dealTitle(a.deal_id)) && (
                    <span className="muted">
                      {" "}· {[contactName(a.contact_id), dealTitle(a.deal_id)].filter(Boolean).join(" · ")}
                    </span>
                  )}
                  <small>{fmtDateTime(a.created_at)}</small>
                </div>
              ))}
            </div>
          </div>
        ))}
        {!shown.length && <p className="muted">No activity recorded yet. It builds up as the team works contacts, deals and tasks.</p>}
      </div>
    </>
  );
}
