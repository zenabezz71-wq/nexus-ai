"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "../../lib/api";

type Webhook = { url: string; note: string } | null;
type Integration = { key: string; name: string; status: string; reason: string };

export default function IntegrationsPage() {
  const [webhook, setWebhook] = useState<Webhook>(null);
  const [items, setItems] = useState<Integration[]>([]);
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);

  async function load() {
    const d = await apiFetch("/integrations");
    setWebhook(d.webhook); setItems(d.integrations);
  }
  useEffect(() => { load().catch((e) => setNote(e.message)); }, []);

  async function rotate() {
    if (!confirm("Rotate the webhook URL? The current one stops working immediately.")) return;
    try {
      const d = await apiFetch("/integrations/webhook-key/rotate", { method: "POST" });
      setWebhook({ url: d.url, note: d.note }); setNote("Webhook URL rotated. Update any tool using the old URL.");
    } catch (err) { setNote(err instanceof Error ? err.message : "Rotate failed"); }
  }
  async function copy() {
    if (!webhook) return;
    try { await navigator.clipboard.writeText(webhook.url); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { setNote("Copy failed — select the URL manually."); }
  }

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">Workspace</span><h1 style={{ margin: "6px 0" }}>Integrations</h1></div>
      </div>
      <p className="muted">How leads and data flow in and out of this workspace. Statuses here are honest: not connected means not connected.</p>
      {note && <p className="alert" role="status">{note}</p>}

      {webhook && (
        <div className="panel" style={{ margin: 0 }}>
          <h2 style={{ marginTop: 0 }}>Inbound webhook <span className="tag">live</span></h2>
          <p>Push leads into this workspace from any external tool with one POST:</p>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12 }}>{`curl -X POST ${webhook.url} \\
  -H "Content-Type: application/json" \\
  -d '{"phone": "+2010...", "name": "Lead name", "goal": "what they asked for"}'`}</pre>
          <p className="muted">Same phone number twice never creates a duplicate — the second call returns the existing lead. {webhook.note}</p>
          <div className="row">
            <button className="btn alt" type="button" onClick={copy}>{copied ? "Copied" : "Copy URL"}</button>
            <button className="btn alt" type="button" onClick={rotate}>Rotate URL</button>
          </div>
        </div>
      )}
      {!webhook && (
        <div className="panel" style={{ margin: 0 }}>
          <h2 style={{ marginTop: 0 }}>Inbound webhook</h2>
          <p className="muted">Your role can view integration status. An owner or admin manages the webhook URL.</p>
        </div>
      )}

      <div className="panel" style={{ margin: 0 }}>
        <h2 style={{ marginTop: 0 }}>Planned integrations</h2>
        <table>
          <thead><tr><th>Integration</th><th>Status</th><th>What it needs</th></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.key}>
                <td>{i.name}</td>
                <td><span className="tag">{i.status.replace(/_/g, " ")}</span></td>
                <td><small className="muted">{i.reason}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
