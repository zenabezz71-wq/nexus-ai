"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDate, fmtDateTime, Me } from "../../lib/api";

type Stage = { id: number; name: string; position: number; probability: number; is_won: boolean; is_lost: boolean };
type Pipeline = { id: number; name: string; is_default: boolean; stages: Stage[] };
type Deal = {
  id: number; title: string; contact_id: number | null; stage_id: number | null;
  amount: number | null; currency: string; expected_close: string | null;
  probability: number; status: string; next_step: string; last_activity_at: string | null;
};
type Contact = { id: number; name: string };
type Activity = { id: number; kind: string; body: string; user_id: number; created_at: string | null };

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
  const [selected, setSelected] = useState<Deal | null>(null);
  const [dealActs, setDealActs] = useState<Activity[]>([]);
  const [editForm, setEditForm] = useState({ title: "", amount: "", expected_close: "", next_step: "", stage_id: "" });
  const [noteBody, setNoteBody] = useState("");
  const [manage, setManage] = useState(false);
  const [stageForm, setStageForm] = useState({ name: "", probability: "0" });
  const [rename, setRename] = useState<Record<number, string>>({});

  async function load(keepSelection = false) {
    const [pipes, ds, cs] = await Promise.all([
      apiFetch("/pipelines"), apiFetch("/deals"), apiFetch("/contacts"),
    ]);
    setPipeline(pipes[0] || null); setDeals(ds); setContacts(cs);
    if (keepSelection && selected) {
      const still = ds.find((d: Deal) => d.id === selected.id);
      setSelected(still || null);
      if (still) loadActs(still.id);
    }
  }
  async function loadActs(dealId: number) {
    setDealActs(await apiFetch(`/activities?deal_id=${dealId}&limit=100`));
  }
  useEffect(() => {
    apiFetch("/auth/me").then(setMe).catch(() => {});
    load().catch((e) => setNote(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const perms = me?.permissions || [];
  const canDelete = me ? (me.permissions ? perms.includes("deals.delete") : ["owner", "admin"].includes(me.role)) : false;
  const canManage = me ? (me.permissions ? perms.includes("company.settings") : ["owner", "admin"].includes(me.role)) : false;
  const contactName = (id: number | null) => (id == null ? "" : contacts.find((c) => c.id === id)?.name || "");

  function selectDeal(d: Deal) {
    setSelected(d);
    setEditForm({
      title: d.title, amount: d.amount != null ? String(d.amount) : "",
      expected_close: d.expected_close ? d.expected_close.slice(0, 10) : "",
      next_step: d.next_step, stage_id: d.stage_id ? String(d.stage_id) : "",
    });
    setNoteBody("");
    loadActs(d.id).catch((e) => setNote(e.message));
  }

  async function move(dealId: number, stageId: number) {
    const deal = deals.find((d) => d.id === dealId);
    if (!deal || deal.stage_id === stageId) return;
    setDeals(deals.map((d) => (d.id === dealId ? { ...d, stage_id: stageId } : d)));
    try {
      const updated = await apiFetch(`/deals/${dealId}`, { method: "PATCH", body: JSON.stringify({ stage_id: stageId }) });
      setDeals((cur) => cur.map((d) => (d.id === dealId ? { ...d, ...updated } : d)));
      if (selected?.id === dealId) { setSelected((cur) => (cur ? { ...cur, ...updated } : cur)); loadActs(dealId); }
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
      setCreating(false); await load(true);
    } catch (err) { setNote(err instanceof Error ? err.message : "Save failed"); }
    finally { setBusy(false); }
  }
  async function submitEdit(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return; setBusy(true); setNote("");
    try {
      const body: Record<string, unknown> = {
        title: editForm.title,
        amount: editForm.amount ? Number(editForm.amount) : null,
        expected_close: editForm.expected_close || null,
        next_step: editForm.next_step,
      };
      if (editForm.stage_id && Number(editForm.stage_id) !== selected.stage_id) body.stage_id = Number(editForm.stage_id);
      const updated = await apiFetch(`/deals/${selected.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setSelected({ ...selected, ...updated });
      await load(true); await loadActs(selected.id);
      setNote("Deal updated.");
    } catch (err) { setNote(err instanceof Error ? err.message : "Update failed"); }
    finally { setBusy(false); }
  }
  async function addNote(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !noteBody.trim()) return; setBusy(true);
    try {
      await apiFetch("/activities", { method: "POST", body: JSON.stringify({ kind: "note", body: noteBody.trim(), deal_id: selected.id }) });
      setNoteBody(""); await loadActs(selected.id);
    } catch (err) { setNote(err instanceof Error ? err.message : "Note failed"); }
    finally { setBusy(false); }
  }
  async function doDelete(id: number) {
    setBusy(true);
    try {
      await apiFetch(`/deals/${id}`, { method: "DELETE" });
      if (selected?.id === id) setSelected(null);
      await load();
    } catch (err) { setNote(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  // ---- stage management ----
  async function addStage(e: React.FormEvent) {
    e.preventDefault(); if (!pipeline) return; setBusy(true); setNote("");
    try {
      await apiFetch(`/pipelines/${pipeline.id}/stages`, {
        method: "POST", body: JSON.stringify({ name: stageForm.name, probability: Number(stageForm.probability) || 0 }),
      });
      setStageForm({ name: "", probability: "0" }); await load(true);
    } catch (err) { setNote(err instanceof Error ? err.message : "Add stage failed"); }
    finally { setBusy(false); }
  }
  async function patchStage(id: number, body: Record<string, unknown>) {
    try { await apiFetch(`/stages/${id}`, { method: "PATCH", body: JSON.stringify(body) }); await load(true); }
    catch (err) { setNote(err instanceof Error ? err.message : "Stage update failed"); }
  }
  async function moveStage(s: Stage, dir: -1 | 1) {
    if (!pipeline) return;
    const ordered = [...pipeline.stages].sort((a, b) => a.position - b.position || a.id - b.id);
    const i = ordered.findIndex((x) => x.id === s.id);
    const other = ordered[i + dir];
    if (!other) return;
    setBusy(true);
    try {
      await apiFetch(`/stages/${s.id}`, { method: "PATCH", body: JSON.stringify({ position: other.position }) });
      await apiFetch(`/stages/${other.id}`, { method: "PATCH", body: JSON.stringify({ position: s.position }) });
      await load(true);
    } catch (err) { setNote(err instanceof Error ? err.message : "Reorder failed"); }
    finally { setBusy(false); }
  }
  async function deleteStage(s: Stage) {
    setBusy(true); setNote("");
    try { await apiFetch(`/stages/${s.id}`, { method: "DELETE" }); await load(true); }
    catch (err) { setNote(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">CRM</span><h1 style={{ margin: "6px 0" }}>{pipeline?.name || "Pipeline"}</h1></div>
        <div className="row">
          {canManage && <button className="btn alt" type="button" onClick={() => setManage(!manage)}>{manage ? "Done managing" : "Manage stages"}</button>}
          <button className="btn" type="button" onClick={() => setCreating(!creating)}>{creating ? "Close" : "New deal"}</button>
        </div>
      </div>
      <p className="muted">Drag a deal between stages, or open it for details. Every move is saved to the activity timeline.</p>
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
      <div style={{ display: "grid", gridTemplateColumns: selected ? "minmax(0,1fr) 340px" : "1fr", gap: 18, alignItems: "start" }}>
        <div>
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
                  {manage ? (
                    <div style={{ display: "grid", gap: 6, marginBottom: 8 }}>
                      <input value={rename[s.id] ?? s.name} maxLength={120}
                             onChange={(e) => setRename({ ...rename, [s.id]: e.target.value })}
                             onBlur={() => { const v = (rename[s.id] ?? s.name).trim(); if (v && v !== s.name) patchStage(s.id, { name: v }); }} />
                      <div className="row" style={{ gap: 4 }}>
                        <button className="btn alt mini" type="button" disabled={busy} title="Move left" onClick={() => moveStage(s, -1)}>◀</button>
                        <button className="btn alt mini" type="button" disabled={busy} title="Move right" onClick={() => moveStage(s, 1)}>▶</button>
                        <input type="number" min="0" max="100" title="Win probability %"
                               style={{ width: 64, minWidth: 0, padding: "6px 8px" }}
                               value={rename[-s.id] ?? String(s.probability)}
                               onChange={(e) => setRename({ ...rename, [-s.id]: e.target.value })}
                               onBlur={() => { const v = Number(rename[-s.id] ?? s.probability); if (!Number.isNaN(v) && v !== s.probability) patchStage(s.id, { probability: v }); }} />
                        <button className="btn alt mini" type="button" disabled={busy} title="Delete stage" onClick={() => deleteStage(s)}>🗑</button>
                      </div>
                    </div>
                  ) : (
                    <h3 style={{ cursor: "pointer" }} onClick={() => setManage(false)}>{s.name}{s.is_won ? " 🏆" : s.is_lost ? " ✕" : ""}</h3>
                  )}
                  <div className="count">{inStage.length} deal{inStage.length === 1 ? "" : "s"}{total ? ` · ${total.toLocaleString()} EGP` : ""} · {s.probability}%</div>
                  {inStage.map((d) => (
                    <div key={d.id} className="card" draggable
                         style={selected?.id === d.id ? { borderColor: "var(--accent)" } : undefined}
                         onClick={() => selectDeal(d)}
                         onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(d.id)); e.dataTransfer.effectAllowed = "move"; }}>
                      <div className="workspace-heading" style={{ gap: 6 }}>
                        <strong>{d.title}</strong>
                        {canDelete && <button className="btn alt mini" type="button" disabled={busy} title="Archive deal"
                                              onClick={(e) => { e.stopPropagation(); doDelete(d.id); }}>✕</button>}
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
            {manage && (
              <div className="col" style={{ borderStyle: "dashed" }}>
                <h3>Add stage</h3>
                <form onSubmit={addStage} style={{ display: "grid", gap: 8 }}>
                  <input required maxLength={120} placeholder="Stage name" value={stageForm.name} onChange={(e) => setStageForm({ ...stageForm, name: e.target.value })} />
                  <label className="muted" style={{ display: "grid", gap: 4 }}>Win probability %
                    <input type="number" min="0" max="100" value={stageForm.probability} onChange={(e) => setStageForm({ ...stageForm, probability: e.target.value })} />
                  </label>
                  <button className="btn" disabled={busy} type="submit">Add stage</button>
                </form>
              </div>
            )}
          </div>
          {!pipeline && !note && <p className="muted">Loading pipeline...</p>}
        </div>
        {selected && (
          <div className="panel" style={{ margin: 0 }}>
            <div className="workspace-heading" style={{ marginBottom: 8 }}>
              <h2 style={{ margin: 0, fontSize: 20 }}>{selected.title}</h2>
              <button className="btn alt mini" type="button" onClick={() => setSelected(null)}>Close</button>
            </div>
            <div style={{ display: "grid", gap: 4, fontSize: 14, marginBottom: 12 }}>
              {contactName(selected.contact_id) && <div><span className="muted">Contact: </span>{contactName(selected.contact_id)}</div>}
              <div><span className="muted">Status: </span><span className="tag">{selected.status}</span> <span className="muted">· probability {selected.probability}%</span></div>
              {selected.last_activity_at && <div><span className="muted">Last activity: </span>{fmtDateTime(selected.last_activity_at)}</div>}
            </div>
            <form onSubmit={submitEdit} style={{ display: "grid", gap: 10 }}>
              <label style={{ display: "grid", gap: 4, fontSize: 13 }}>Title
                <input required maxLength={200} value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} /></label>
              <label style={{ display: "grid", gap: 4, fontSize: 13 }}>Stage
                <select value={editForm.stage_id} onChange={(e) => setEditForm({ ...editForm, stage_id: e.target.value })}>
                  {(pipeline?.stages || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select></label>
              <label style={{ display: "grid", gap: 4, fontSize: 13 }}>Amount (EGP)
                <input type="number" min="0" step="0.01" value={editForm.amount} onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })} /></label>
              <label style={{ display: "grid", gap: 4, fontSize: 13 }}>Expected close
                <input type="date" value={editForm.expected_close} onChange={(e) => setEditForm({ ...editForm, expected_close: e.target.value })} /></label>
              <label style={{ display: "grid", gap: 4, fontSize: 13 }}>Next step
                <input maxLength={300} value={editForm.next_step} onChange={(e) => setEditForm({ ...editForm, next_step: e.target.value })} /></label>
              <button className="btn" disabled={busy} type="submit">Save changes</button>
            </form>
            <h3>Activity</h3>
            <form className="row" onSubmit={addNote} style={{ marginBottom: 10 }}>
              <input required maxLength={10000} placeholder="Log what happened..." value={noteBody} onChange={(e) => setNoteBody(e.target.value)} style={{ flex: 1, minWidth: 140 }} />
              <button className="btn alt" disabled={busy} type="submit">Log</button>
            </form>
            <div className="timeline">
              {dealActs.map((a) => (
                <div className="ev" key={a.id}><span className="tag">{a.kind}</span> {a.body}<small>{fmtDateTime(a.created_at)}</small></div>
              ))}
              {!dealActs.length && <p className="muted">No activity yet.</p>}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
