"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDateTime } from "../../lib/api";

type Entry = { id: number; action: string; actor: string; details: Record<string, unknown>; created_at: string | null };

export default function AuditPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [note, setNote] = useState("");

  useEffect(() => {
    apiFetch("/audit-log").then((d) => setEntries(d.entries)).catch((e) => setNote(e.message));
  }, []);

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">Workspace</span><h1 style={{ margin: "6px 0" }}>Audit Log</h1></div>
      </div>
      <p className="muted">Every sensitive action in this workspace, newest first. Read-only — entries are written by the system when actions happen. Visible to owner and admin only.</p>
      {note && <p className="alert" role="status">{note}</p>}
      <div className="panel" style={{ margin: 0 }}>
        {entries.length > 0 && (
          <table>
            <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td style={{ whiteSpace: "nowrap" }}><small>{fmtDateTime(e.created_at)}</small></td>
                  <td>{e.actor}</td>
                  <td><span className="tag">{e.action}</span></td>
                  <td><small className="muted" style={{ wordBreak: "break-all" }}>{JSON.stringify(e.details)}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!entries.length && !note && <p className="muted">No entries yet. Sensitive actions (imports, conversions, exports, deletions, webhook events) appear here as they happen.</p>}
      </div>
    </>
  );
}
