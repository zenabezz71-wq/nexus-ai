"use client";
import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Msg = { id: number; role: "customer" | "assistant" | "human"; body: string; delivery: string };
type Fb = { id: number; body: string; author: string };
type Conv = {
  id: number; mode: "ai" | "human"; channel: string; needs_attention: boolean; handoff_reason: string; lead_id: number; lead_name: string; lead_status: string; last_message: string;
  messages?: Msg[];
  lead?: { name: string; status: string; goal: string; amount: number | null; currency: string; confidence: number; reason: string; opted_out: boolean; feedback: Fb[] };
  qualification?: { goal: string; budget: number | null; currency: string; timeline: string; name: string; score: number };
};
const STATUS: Record<string, string> = { unclassified: "غير مصنف", hot_lead: "🔥 ساخن", warm_lead: "دافئ", cold_lead: "بارد", follow_up: "متابعة لاحقاً", not_interested: "غير مهتم", won: "تم البيع", lost: "خسارة", contacted: "تم التواصل", qualified: "مؤهل" };
const TIMELINE: Record<string, string> = { soon: "قريب جداً", mid: "متوسط", later: "بعيد" };
const SAMPLES = ["السلام عليكم", "بكام الباقات عندكم؟", "عايز أعمل موقع لمتجري", "ميزانيتي ٨٠٠٠ جنيه", "محتاجه في أسرع وقت", "عايز أكلم حد من الفريق", "وقف الرسائل"];

export default function Assistant({ token, onOpenLead, onChange }: { token: string; onOpenLead: (id: number) => void; onChange: () => void }) {
  const [list, setList] = useState<Conv[]>([]);
  const [cur, setCur] = useState<Conv | null>(null);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const end = useRef<HTMLDivElement>(null);

  async function call(path: string, init: RequestInit = {}) {
    const r = await fetch(API + path, { ...init, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
    const d = await r.json();
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Request failed");
    return d;
  }
  async function loadList() { try { setList(await call("/assistant/conversations")); } catch (e) { setNote(e instanceof Error ? e.message : "Failed"); } }
  useEffect(() => { loadList(); }, [token]);
  useEffect(() => { const box = end.current?.parentElement; if (box) box.scrollTop = box.scrollHeight; }, [cur?.messages?.length]);

  async function act(path: string, init: RequestInit = {}, after?: () => void) {
    setBusy(true); setNote("");
    try { const d = await call(path, init); if (after) after(); else setCur(d); await loadList(); onChange(); } catch (e) { setNote(e instanceof Error ? e.message : "Failed"); }
    setBusy(false);
  }
  const start = () => act("/assistant/simulations", { method: "POST", body: JSON.stringify({ customer_name: name }) }, undefined).then(() => setName(""));
  async function send(body: string) {
    if (!cur || !body.trim()) return;
    setText("");
    await act(`/assistant/conversations/${cur.id}/${cur.mode === "human" ? "human-reply" : "messages"}`, { method: "POST", body: JSON.stringify({ body }) });
  }
  const alerts = list.filter(c => c.needs_attention);

  return <section className="panel assistant" id="assistant">
    <div className="row" style={{ justifyContent: "space-between" }}>
      <div><span className="eyebrow">AI SALES ASSISTANT · DEMO MODE</span><h2 style={{ margin: "6px 0" }}>المساعد الذكي للردود</h2></div>
      <span className="tag">Rule-based Arabic engine · no AI service · nothing is sent</span>
    </div>
    <p className="muted">جرّبي دور العميل واكتبي رسالة بالعربي أو بالعامية. المساعد بيرد، بيسأل أسئلة التأهيل، بيحدّث سجل العميل في الـCRM، وبينبّه المبيعات لما العميل يبقى ساخن. الواتساب الحقيقي لسه مقفول لحد ربط حساب Meta الرسمي.</p>
    {alerts.length > 0 && <div className="alert" role="alert">🔥 {alerts.length} محادثة محتاجة تدخل بشري: {alerts.map(c => <button key={c.id} className="btn alt mini" onClick={() => act(`/assistant/conversations/${c.id}`, {}, undefined)}>{c.lead_name}: {c.handoff_reason}</button>)}</div>}
    <div className="assistant-grid">
      <div className="assistant-side">
        <div className="row"><input value={name} onChange={e => setName(e.target.value)} placeholder="اسم العميل التجريبي (اختياري)" maxLength={60} dir="rtl" /><button className="btn" disabled={busy} onClick={start}>محادثة تجريبية جديدة</button></div>
        <ul className="conv-list">{list.map(c => <li key={c.id}><button className={"conv-item" + (cur?.id === c.id ? " on" : "")} onClick={() => act(`/assistant/conversations/${c.id}`, {}, undefined)}>
          <strong>{c.lead_name}</strong>{c.needs_attention && <span className="flag">🔥</span>}<small>{STATUS[c.lead_status] || c.lead_status} · {c.mode === "human" ? "مندوب" : "مساعد"}</small><small>{c.last_message}</small></button></li>)}
          {list.length === 0 && <li className="muted">لا توجد محادثات بعد. ابدئي واحدة تجريبية.</li>}</ul>
      </div>
      <div className="assistant-main">
        {!cur ? <p className="muted">اختاري محادثة أو ابدئي واحدة جديدة.</p> : <>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{cur.lead?.name || cur.lead_name}</strong>
            <div className="row">
              {cur.mode === "ai" ? <button className="btn alt mini" disabled={busy} onClick={() => act(`/assistant/conversations/${cur.id}/takeover`, { method: "POST" })}>👤 استلام المحادثة</button> : <button className="btn alt mini" disabled={busy} onClick={() => act(`/assistant/conversations/${cur.id}/release`, { method: "POST" })}>🤖 إرجاع للمساعد</button>}
              {cur.needs_attention && <button className="btn alt mini" disabled={busy} onClick={() => act(`/assistant/conversations/${cur.id}/ack`, { method: "POST" })}>تم الاطلاع ✔</button>}
              <button className="btn alt mini" onClick={() => onOpenLead(cur.lead_id)}>فتح سجل العميل</button>
              <button className="btn alt mini" disabled={busy} onClick={() => act(`/assistant/conversations/${cur.id}`, { method: "DELETE" }, () => setCur(null))}>حذف</button>
            </div>
          </div>
          {cur.needs_attention && <div className="alert">🔥 تنبيه للمبيعات: {cur.handoff_reason}</div>}
          <div className="chat" dir="rtl">{(cur.messages || []).map(m => <div key={m.id} className={"bubble " + m.role}><small>{m.role === "customer" ? "العميل" : m.role === "assistant" ? "🤖 المساعد" : "👤 المندوب"}</small>{m.body}</div>)}<div ref={end} /></div>
          <div className="row" style={{ marginBottom: 8 }}>{SAMPLES.map(s => <button key={s} className="btn alt mini" disabled={busy || cur.mode === "human"} onClick={() => send(s)}>{s}</button>)}</div>
          <form className="row" onSubmit={e => { e.preventDefault(); send(text); }}>
            <input style={{ flex: 1 }} dir="rtl" value={text} onChange={e => setText(e.target.value)} maxLength={2000} placeholder={cur.mode === "human" ? "رد المندوب (تجريبي، لا يُرسل لأحد)" : "اكتبي كأنك العميل..."} />
            <button className="btn" disabled={busy || !text.trim()}>{cur.mode === "human" ? "رد كمندوب" : "إرسال كعميل"}</button>
          </form>
          <div className="lead-card"><h3>سجل العميل (يتحدث لايف)</h3>
            <div className="row"><span className="tag">{STATUS[cur.lead?.status || ""] || cur.lead?.status}</span>{cur.lead && <span className="muted">ثقة {Math.round(cur.lead.confidence * 100)}% · {cur.lead.reason}</span>}{cur.lead?.opted_out && <span className="tag">عدم تواصل</span>}</div>
            <ul className="qual"><li>الاحتياج: {cur.qualification?.goal || "—"}</li><li>الميزانية: {cur.qualification?.budget != null ? `${cur.qualification.budget} ${cur.qualification.currency}` : "—"}</li><li>التوقيت: {TIMELINE[cur.qualification?.timeline || ""] || "—"}</li><li>الاسم: {cur.qualification?.name || "—"}</li></ul>
            <strong>ملاحظات وتسليم</strong>{(cur.lead?.feedback || []).slice(0, 5).map(f => <p key={f.id} className="fb">{f.body}</p>)}{!(cur.lead?.feedback || []).length && <p className="muted">لا توجد ملاحظات بعد.</p>}
          </div></>}
        {note && <p className="alert" role="status">{note}</p>}
      </div>
    </div>
  </section>;
}
