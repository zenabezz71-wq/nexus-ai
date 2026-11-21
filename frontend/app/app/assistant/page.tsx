"use client";
import { useState } from "react";
import { apiFetch } from "../../lib/api";

type Turn = { q: string; answer: string; method: string; intent: string };

const SUGGESTED = [
  "مين محتاج متابعة النهارده؟",
  "من أفضل موظف مبيعات الشهر ده؟",
  "إيه الصفقات اللي ممكن نخسرها؟",
  "اعمل تقرير مبيعات الشهر ده",
  "اكتب رسالة متابعة",
  "إحصائيات العملاء المحتملين",
];

export default function AssistantPage() {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setBusy(true); setNote("");
    try {
      const d = await apiFetch("/copilot/ask", { method: "POST", body: JSON.stringify({ question }) });
      setTurns((t) => [{ q: question, answer: d.answer, method: d.method, intent: d.intent }, ...t]);
      setQ("");
    } catch (err) { setNote(err instanceof Error ? err.message : "Request failed"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">Workspace</span><h1 style={{ margin: "6px 0" }}>AI Assistant</h1></div>
      </div>
      <p className="muted">
        Ask about your workspace in Arabic or English. Every answer is computed from your live data and labeled with the method used.
      </p>
      {note && <p className="alert" role="status">{note}</p>}
      <div className="panel" style={{ margin: 0 }}>
        <form onSubmit={(e) => { e.preventDefault(); ask(q); }} style={{ display: "flex", gap: 8 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="اسأل عن الشغل... / Ask about your workspace..." style={{ flex: 1 }} />
          <button className="btn" type="submit" disabled={busy}>{busy ? "Thinking..." : "Ask"}</button>
        </form>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
          {SUGGESTED.map((s) => (
            <button key={s} className="btn alt mini" type="button" onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
      </div>
      <div className="timeline" style={{ marginTop: 12 }}>
        {turns.map((t, i) => (
          <div className="ev panel" style={{ margin: 0 }} key={i}>
            <strong>{t.q}</strong>
            <p style={{ whiteSpace: "pre-wrap", margin: "8px 0" }}>{t.answer}</p>
            <small className="muted">Method: {t.method}</small>
          </div>
        ))}
        {!turns.length && <p className="muted">No questions yet. Try one of the suggested prompts above.</p>}
      </div>
    </>
  );
}
