"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDate, Me } from "../../lib/api";

type Stage = { id: number; name: string; position: number; probability: number; is_won: boolean; is_lost: boolean };
type Pipeline = { id: number; name: string; is_default: boolean; stages: Stage[] };
type Deal = {
  id: number; title: string; contact_id: number | null; stage_id: number | null;
  amount: number | null; currency: string; expected_close: string | null;
  probability: number; status: string; next_step: string;
};
type Contact = { id: number; name: string };

export default function PipelinePage() {
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", contact_id: "", amount: "", expected_close: "", next_step: "" });
  const [dragOver, setDragOver] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [pipes, ds, cs] = await Promise.all([
      apiFetch("/pipelines"), apiFetch("/deals"), apiFetch("/contacts"),
    ]);
    setPipeline(pipes[0] || null); setDeals(ds); setContacts(cs);
  }
  useEffect(() => {
    apiFetch("/auth/me").then(setMe).catch(() => {});
    load().catch((e) => setNote(e.message));
  }, []);

  const canDelete = me ? (me.permissions ? me.permissions.includes("deals.delete") : ["owner", "admin"].includes(me.role)) : false;
  const contactName = (id: number | null) => (id == null ? "" : contacts.find((c) => c.id === id)?.name || "");

  async function move(dealId: number, stageId: number) {
    const deal = deals.find((d) => d.id === dealId);
    if (!deal || deal.stage_id === stageId) return;
    setDeals(deals.map((d) => (d.id === dealId ? { ...d, stage_id: stageId } : d)));
    try {
      const updated = await apiFetch(`/deals/${dealId}`, { method: "PATCH", body: JSON.stringify({ stage_id: stageId }) });
      setDeals((cur) => cur.map((d) => (d.id === dealId ? { ...d, ...updated } : d)));
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Move failed");
      load().catch(() => {});
    }
  }
  async function submitCreate(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setNote("");
    try {
      await apiFetch("/deals", {
        method: "POST",
        body: JSON.stringify({
          title: form.title,
          contact_id: form.contact_id ? Number(form.contact_id) : null,
          amount: form.amount ? Number(form.amount) : null,
          expected_close: form.expected_close || null,
          next_step: form.next_step,
        }),
      });
      setForm({ title: "", contact_id: "", amount: "", expected_close: "", next_step: "" });
      setCreating(false); await load();
    } catch (err) { setNote(err instanceof Error ? err.message : "Save failed"); }
    finally { setBusy(false); }
  }
  async function doDelete(id: number) {
    setBusy(true);
    try { await apiFetch(`/deals/${id}`, { method: "DELETE" }); await load(); }
    catch (err) { setNote(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">CRM</span><h1 style={{ margin: "6px 0" }}>{pipeline?.name || "Pipeline"}</h1></div>
        <button className="btn" type="button" onClick={() => setCreating(!creating)}>{creating ? "Close" : "New deal"}</button>
      </div>
      <p className="muted">Drag a deal between stages. Every move is saved to the activity timeline.</p>
      {note && <p className="alert" role="status">{note}</p>}
      {creating && (
        <form className="panel" onSubmit={submitCreate}>
          <h3 style={{ marginTop: 0 }}>New deal</h3>
          <div className="crm-grid">
            <label>Title *<input required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
            <label>Contact
              <select value={form.contact_id} onChange={(e) => setForm({ ...form, contact_id: e.target.value })}>
                <option value="">None yet</option>
                {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label>Amount (EGP)<input type="number" min="0" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
            <label>Expected close<input type="date" value={form.expected_close} onChange={(e) => setForm({ ...form, expected_close: e.target.value })} /></label>
            <label style={{ gridColumn: "1/-1" }}>Next step<input maxLength={300} value={form.next_step} onChange={(e) => setForm({ ...form, next_step: e.target.value })} /></label>
          </div>
          <div className="row" style={{ marginTop: 12 }}><button className="btn" disabled={busy} type="submit">Create deal</button></div>
        </form>
      )}
      <div className="board">
        {(pipeline?.stages || []).map((s) => {
          const inStage = deals.filter((d) => d.stage_id === s.id);
          const total = inStage.reduce((sum, d) => sum + (d.amount || 0), 0);
          return (
            <div key={s.id}
                 className={"col" + (dragOver === s.id ? " drop" : "")}
                 onDragOver={(e) => { e.preventDefault(); setDragOver(s.id); }}
                 onDragLeave={() => setDragOver((cur) => (cur === s.id ? null : cur))}
                 onDrop={(e) => { e.preventDefault(); setDragOver(null); const id = Number(e.dataTransfer.getData("text/plain")); if (id) move(id, s.id); }}>
              <h3>{s.name}{s.is_won ? " 🏆" : s.is_lost ? " ✕" : ""}</h3>
              <div className="count">{inStage.length} deal{inStage.length === 1 ? "" : "s"}{total ? ` · ${total.toLocaleString()} EGP` : ""}</div>
              {inStage.map((d) => (
                <div key={d.id} className="card" draggable
                     onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(d.id)); e.dataTransfer.effectAllowed = "move"; }}>
                  <div className="workspace-heading" style={{ gap: 6 }}>
                    <strong>{d.title}</strong>
                    {canDelete && <button className="btn alt mini" type="button" disabled={busy} title="Archive deal" onClick={() => doDelete(d.id)}>✕</button>}
                  </div>
                  {contactName(d.contact_id) && <div className="muted">{contactName(d.contact_id)}</div>}
                  {d.amount != null && <div className="amt">{d.amount.toLocaleString()} {d.currency}</div>}
                  {d.next_step && <div style={{ marginTop: 4 }}>{d.next_step}</div>}
                  {d.expected_close && <div className="muted">Close: {fmtDate(d.expected_close)}</div>}
                </div>
              ))}
              {!inStage.length && <div className="muted" style={{ padding: "6px 2px" }}>Drop deals here</div>}
            </div>
          );
        })}
      </div>
      {!pipeline && !note && <p className="muted">Loading pipeline...</p>}
    </>
  );
}
