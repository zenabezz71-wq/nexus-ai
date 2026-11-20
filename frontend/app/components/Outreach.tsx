"use client";
import { useEffect, useState } from "react";

type Lead = { id: number; name: string; email: string; phone: string; consent: boolean; opted_out?: boolean };
type Log = { lead_id: number; recipient: string; status: string; error: string };
type Status = { ready: boolean; blockers: string[]; daily_cap: number; remaining_today: number; attempts_today: number; logs: Log[]; template?: { subject: string; body: string } };
type Preview = { messages: { lead_id: number; recipient: string; subject?: string; body: string; demo_only?: boolean }[]; skipped: { lead_id: number; reason: string }[]; review_token: string; blockers: string[]; sender?: { name: string; email: string } };
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Outreach({ token, leads }: { token: string; leads: Lead[] }) {
  const [channel, setChannel] = useState<"email" | "whatsapp">("email");
  const [status, setStatus] = useState<Status | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const path = channel === "email" ? "/outreach" : "/whatsapp";

  async function request(endpoint: string, init: RequestInit = {}) {
    const r = await fetch(API + endpoint, { ...init, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed");
    return data;
  }
  async function refresh() {
    const data = await request(path + "/status");
    setStatus(data);
    if (data.template) { setSubject(data.template.subject); setBody(data.template.body); }
  }
  useEffect(() => { setPreview(null); setSelected([]); setStatus(null); setNote(""); refresh().catch(e => setNote(e.message)); }, [channel, token]); // eslint-disable-line react-hooks/exhaustive-deps
  async function perform(fn: () => Promise<void>) {
    setBusy(true); setNote("");
    try { await fn(); } catch (e) { setNote(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  const eligible = leads.filter(x => x.consent && !x.opted_out && (channel === "email" ? Boolean(x.email) : Boolean(x.phone)));
  return <section className="panel" id="outreach" aria-label="Outreach">
    <h2>Outreach</h2>
    <p className="muted">Preview personalized messages, then choose whether to send. Imports never send messages. Only select people who explicitly opted in to this channel. Sample leads are not permission to contact anyone.</p>
    <div className="row" style={{ marginBottom: 16 }}>
      <button type="button" className={channel === "email" ? "btn" : "btn alt"} onClick={() => setChannel("email")} disabled={busy}>Email via Brevo</button>
      <button type="button" className={channel === "whatsapp" ? "btn" : "btn alt"} onClick={() => setChannel("whatsapp")} disabled={busy}>WhatsApp via Meta</button>
      <button type="button" className="btn alt" disabled={busy} onClick={() => perform(refresh)}>Refresh outreach</button>
    </div>
    <p><strong>{status?.ready ? "Configured for sending" : "Setup required, live sending disabled"}</strong></p>
    {channel === "email" ? <p className="muted">Brevo Free allows 300 emails/day across the account. The app defaults to 250 attempts/day, with a hard ceiling of 290. Other Brevo activity uses the same provider allowance.</p> : <p className="muted">Official WhatsApp Cloud API requires a business account, approved marketing template and credentials. Meta messages can cost money. No account, billing or payment is set up here. STOP replies are processed only after the signed webhook is configured.</p>}
    {status && <p>App quota: {status.remaining_today} / {status.daily_cap} reservations left today (UTC). Attempts today: {status.attempts_today}. Failed or uncertain attempts still count.</p>}
    {!!status?.blockers.length && <ul className="alert">{status.blockers.map(x => <li key={x}>{x}</li>)}</ul>}
    {channel === "email" && <details style={{ margin: "16px 0" }}><summary>Edit email template</summary>
      <p className="muted">Use {"{name}"} and {"{sender_name}"}. Postal address and an unsubscribe link are appended automatically. Review each rendered message before sending.</p>
      <label style={{ display: "block" }}>Subject<input style={{ width: "100%", margin: "8px 0" }} maxLength={200} value={subject} onChange={e => { setSubject(e.target.value); setPreview(null); }} /></label>
      <label style={{ display: "block" }}>Body<textarea style={{ width: "100%", minHeight: 160, padding: 12, margin: "8px 0", font: "inherit", border: "1px solid var(--border)", borderRadius: 8 }} maxLength={10000} value={body} onChange={e => { setBody(e.target.value); setPreview(null); }} /></label>
      <button type="button" className="btn alt" disabled={busy || !subject.trim() || !body.trim()} onClick={() => perform(async () => { await request("/outreach/template", { method: "PUT", body: JSON.stringify({ subject, body }) }); setPreview(null); setNote("Template saved. Generate a fresh preview before sending."); await refresh(); })}>Save template</button>
    </details>}
    <h3>Select recipients, up to 20 per review</h3>
    <p className="muted">This list uses the currently loaded/search-filtered leads. The server rechecks consent, opt-outs, valid addresses, sample contacts and previous attempts.</p>
    <div style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
      {eligible.map(x => <label key={x.id} style={{ display: "block", padding: "8px 0" }}><input type="checkbox" disabled={busy || (!selected.includes(x.id) && selected.length >= 20)} checked={selected.includes(x.id)} onChange={e => { setSelected(e.target.checked ? [...selected, x.id] : selected.filter(id => id !== x.id)); setPreview(null); }} /> {x.name || "Unnamed lead"}, {channel === "email" ? x.email : x.phone}</label>)}
      {!eligible.length && <p>No consent-eligible contacts with a {channel === "email" ? "recorded email" : "phone number"} in the loaded list.</p>}
    </div>
    <div className="row" style={{ marginTop: 16 }}><button type="button" className="btn" disabled={busy || !selected.length} onClick={() => perform(async () => { setPreview(await request(path + "/preview", { method: "POST", body: JSON.stringify({ lead_ids: selected }) })); })}>Preview {selected.length || "selected"} messages</button></div>
    {preview && <div style={{ marginTop: 20 }}><h3>Review exactly what will be sent</h3>
      {preview.sender && <p>From and Reply-To: {preview.sender.name || "Not configured"} &lt;{preview.sender.email || "Not configured"}&gt;</p>}
      {preview.messages.map(m => <article key={m.lead_id} style={{ padding: 16, margin: "12px 0", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8 }}><strong>To: {m.recipient}</strong>{m.demo_only && <p className="alert">Demo preview only, this message cannot be sent.</p>}{m.subject && <p>Subject: {m.subject}</p>}<pre style={{ font: "inherit", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{m.body}</pre></article>)}
      {preview.skipped.map(x => <p key={x.lead_id}>Lead #{x.lead_id} skipped: {x.reason}</p>)}
      {!!preview.blockers.length && <ul className="alert">{preview.blockers.map(x => <li key={x}>{x}</li>)}</ul>}
      <p className="muted">By sending, you confirm these contacts opted in to {channel} marketing and you approve these recipients and words{channel === "whatsapp" ? ", including the applicable Meta charges" : ""}. Review expires in 10 minutes. Each recipient is attempted once, with no automatic retry.</p>
      <button type="button" className="btn" disabled={busy || !preview.messages.length || !!preview.blockers.length || !status?.ready} onClick={() => perform(async () => {
        if (!window.confirm(`Send these ${preview.messages.length} reviewed ${channel} messages${channel === "whatsapp" ? " using Meta's paid messaging service" : ""}?`)) return;
        const result = await request(path + "/send", { method: "POST", body: JSON.stringify({ review_token: preview.review_token }) });
        setPreview(null); setSelected([]); await refresh(); setNote(result.results.map((x: { lead_id: number; status: string; reason?: string }) => `Lead #${x.lead_id}: ${x.status}${x.reason ? " (" + x.reason + ")" : ""}`).join("; ") + ". " + result.note);
      })}>{busy ? "Working..." : "Send reviewed messages"}</button>
    </div>}
    <h3>Recent {channel} attempts</h3>
    <p className="muted">Accepted means the provider accepted the request, not that the message arrived. A stuck sending/unknown result needs provider-dashboard checks, not a blind retry. The latest 100 attempts are shown.</p>
    <div style={{ overflowX: "auto" }}><table><thead><tr><th>Lead</th><th>Recipient</th><th>Status</th><th>Detail</th></tr></thead><tbody>{status?.logs.map((x, i) => <tr key={i}><td>#{x.lead_id}</td><td>{x.recipient}</td><td>{x.status}</td><td>{x.error || ""}</td></tr>)}{!status?.logs.length && <tr><td colSpan={4}>No outreach sent.</td></tr>}</tbody></table></div>
    {note && <p className="alert" role="status">{note}</p>}
  </section>;
    }
