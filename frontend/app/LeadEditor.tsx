"use client";
import { useEffect, useState } from "react";
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Feedback = { id: number; body: string; author: string; created_at: string };
type Detail = { id: number; name: string; phone: string; email: string; goal: string; currency: string; amount: number | null; status: string; consent: boolean; opted_out: boolean; updated_at: string; assigned_user_id: number | null; feedback: Feedback[] };
const statuses = ["unclassified", "hot_lead", "warm_lead", "cold_lead", "follow_up", "not_interested", "contacted", "qualified", "won", "lost", "invalid_number"];
export default function LeadEditor({ id, token, close, changed }: { id: number; token: string; close: () => void; changed: () => Promise<void> }) {
  const [lead, setLead] = useState<Detail | null>(null);
  const [people, setPeople] = useState<{ id: number; name: string }[]>([]);
  const [feedback, setFeedback] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [suppress, setSuppress] = useState(false);
  async function req(path: string, init: RequestInit = {}) {
    const r = await fetch(API + path, { ...init, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
    const data = await r.json();
    if (!r.ok) throw Error(typeof data.detail === "string" ? data.detail : "Invalid data. Check the fields.");
    return data;
  }
  useEffect(() => { setLead(null); setDirty(false); setNote(""); setFeedback(""); setSuppress(false); Promise.all([req(`/leads/${id}`), req("/workspace/salespeople")]).then(([l, p]) => { setLead(l); setPeople(p); }).catch(e => setNote(e.message)); }, [id, token]); // eslint-disable-line react-hooks/exhaustive-deps
  async function run(fn: () => Promise<void>) { setBusy(true); setNote(""); try { await fn(); } catch (e) { setNote(e instanceof Error ? e.message : "Request failed"); } finally { setBusy(false); } }
  function field<K extends keyof Detail>(key: K, value: Detail[K]) { if (lead) { setLead({ ...lead, [key]: value }); setDirty(true); } }
  return <section className="panel" id="lead-editor" aria-label="Lead details and sales feedback">
    <div className="row" style={{ justifyContent: "space-between" }}><h2>Lead #{id}: details and sales feedback</h2><button type="button" className="btn alt" disabled={busy} onClick={()=>{if(!dirty||window.confirm("Discard unsaved lead changes?"))close()}}>Close editor</button></div>
    {!lead ? <p>{note || "Loading lead..."}</p> : <>
      <form onSubmit={e => { e.preventDefault(); run(async () => {
        const { name, phone, email, goal, currency, amount, status, assigned_user_id, updated_at } = lead;
        const saved = await req(`/leads/${id}`, { method: "PATCH", body: JSON.stringify({ name, phone, email, goal, currency, amount, status, assigned_user_id, expected_updated_at: updated_at, do_not_contact: suppress }) });
        setLead(saved); setDirty(false); setSuppress(false); await changed(); setNote("Lead saved. Contact changes reset marketing consent.");
      }); }}>
        <div className="crm-grid">
          <label>Name<input value={lead.name} maxLength={200} onChange={e => field("name", e.target.value)} /></label>
          <label>Phone<input value={lead.phone} required maxLength={40} onChange={e => field("phone", e.target.value)} /></label>
          <label>Email<input type="email" value={lead.email} maxLength={320} onChange={e => field("email", e.target.value)} /></label>
          <label>Status<select value={lead.status} onChange={e => field("status", e.target.value)}>{statuses.map(s => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select></label>
          <label>Salesperson<select value={lead.assigned_user_id ?? ""} onChange={e => field("assigned_user_id", e.target.value ? Number(e.target.value) : null)}><option value="">Unassigned</option>{people.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label>Amount<input type="number" min="0" step="0.01" value={lead.amount ?? ""} onChange={e => field("amount", e.target.value === "" ? null : Number(e.target.value))} /></label>
          <label>Currency<input value={lead.currency} maxLength={12} onChange={e => field("currency", e.target.value)} /></label>
        </div>
        <label style={{ display: "block", marginTop: 12 }}>Goal / lead details<textarea style={{ width: "100%", minHeight: 100 }} maxLength={10000} value={lead.goal} onChange={e => field("goal", e.target.value)} /></label>
        <p className="muted">Marketing consent: {lead.consent ? "Recorded" : "Not recorded"}. Contact restriction: {lead.opted_out ? "Do not contact" : "Not opted out"}. Changing an email or phone resets consent. This editor cannot grant consent or remove an opt-out.</p>
        {!lead.opted_out && <label style={{ display: "block", margin: "12px 0" }}><input type="checkbox" checked={suppress} onChange={e => setSuppress(e.target.checked)} /> Mark do not contact and suppress outreach</label>}
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving..." : "Save lead details"}</button>
      </form>
      <h3>Sales feedback</h3><p className="muted">Each note records its author and time. Notes are kept as a history, not overwritten. Save detail changes before adding feedback.</p>
      <form onSubmit={e => { e.preventDefault(); run(async () => { const result = await req(`/leads/${id}/feedback`, { method: "POST", body: JSON.stringify({ body: feedback }) }); setLead(result); setFeedback(""); setNote("Feedback added."); }); }}>
        <label>New feedback<textarea style={{ display: "block", width: "100%", minHeight: 90, margin: "8px 0" }} value={feedback} maxLength={5000} onChange={e => setFeedback(e.target.value)} required placeholder="Call outcome, objections, agreed next step..." /></label>
        <button type="submit" className="btn alt" disabled={busy || dirty || suppress || !feedback.trim()}>Add sales feedback</button>
      </form>
      <div style={{ maxHeight: 360, overflowY: "auto", marginTop: 16 }}>{lead.feedback.map(f => <article key={f.id} style={{ borderTop: "1px solid #e2e7ef", padding: "12px 0" }}><strong>{f.author}</strong><span className="muted"> · {new Date(f.created_at).toLocaleString()}</span><p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{f.body}</p></article>)}{!lead.feedback.length && <p className="muted">No sales feedback yet.</p>}</div>
      {note && <p className="alert" role="status">{note}</p>}
    </>}
  </section>;
          }
