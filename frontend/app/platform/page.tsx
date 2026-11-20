"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Org = {
  id: number; name: string; slug: string; trial_only: boolean;
  is_active: boolean; deleted_at: string | null; created_at: string | null;
  member_count: number; lead_count: number;
};

export default function PlatformPage() {
  const [token, setToken] = useState("");
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [pending, setPending] = useState<{ org: Org; action: "suspend" | "restore" | "delete" } | null>(null);
  const [reason, setReason] = useState("");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = localStorage.getItem("nexus_theme");
    const t = saved === "light" ? "light" : "dark";
    setTheme(t);
    document.documentElement.dataset.theme = t;
  }, []);
  function toggleTheme() {
    const t = theme === "dark" ? "light" : "dark";
    setTheme(t);
    document.documentElement.dataset.theme = t;
    localStorage.setItem("nexus_theme", t);
  }

  function errorText(d: { detail?: unknown }) {
    return typeof d.detail === "string" ? d.detail : Array.isArray(d.detail) ? d.detail.map((x) => x.msg).join(". ") : "Request failed.";
  }
  async function req(path: string, init: RequestInit = {}, t = token) {
    const r = await fetch(API + path, { ...init, headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json", ...(init.headers || {}) } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(errorText(d));
    return d;
  }

  async function load(t: string) {
    try {
      const me = await req("/auth/me", {}, t);
      if (!me.is_platform_admin) { window.location.replace("/"); return; }
      setAllowed(true);
      setOrgs(await req("/platform/organizations", {}, t));
    } catch {
      // Expired or invalid session: sign in again from the main page.
      localStorage.removeItem("nexus_token");
      window.location.replace("/");
    }
  }

  useEffect(() => {
    const t = localStorage.getItem("nexus_token");
    if (!t) { window.location.replace("/"); return; }
    setToken(t);
    load(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function ask(o: Org, action: "suspend" | "restore" | "delete") {
    setPending({ org: o, action });
    setReason("");
    setNote("");
  }

  async function confirmAct() {
    if (!pending) return;
    const { org: o, action } = pending;
    if (reason.trim().length < 3) { setNote("A reason of 3+ characters is required; it is written to the audit log."); return; }
    setBusy(o.id);
    try {
      if (action === "delete") {
        await req(`/platform/organizations/${o.id}?reason=${encodeURIComponent(reason.trim())}`, { method: "DELETE" });
        setNote(`Soft-deleted "${o.name}". Data retained and restorable with the Restore action.`);
      } else {
        await req(`/platform/organizations/${o.id}/${action}`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) });
        setNote(`${action === "suspend" ? "Suspended" : "Restored"} "${o.name}".`);
      }
      setPending(null);
      setOrgs(await req("/platform/organizations"));
    } catch (e) { setNote(e instanceof Error ? e.message : "Action failed"); }
    finally { setBusy(null); }
  }

  return (
    <>
      <header className="top">
        <div>
          <div className="brand"><span className="mark">✦</span> NEXUS AI</div>
          <div className="muted">Platform operations</div>
        </div>
        <div className="row">
          <a className="btn alt" href="/">Workspace</a>
          <button className="btn alt" type="button" onClick={toggleTheme}>{theme === "dark" ? "☀ Light" : "🌙 Dark"}</button>
        </div>
      </header>
      <main className="shell">
        {allowed !== true ? (
          <section className="panel auth-panel"><h1>Loading...</h1></section>
        ) : (
          <>
            <section className="panel workspace-heading">
              <div>
                <span className="eyebrow">PLATFORM OPERATIONS</span>
                <h1>Tenant workspaces</h1>
                <p className="muted">Every action needs a reason and is written to the target workspace's audit log. Deletion is a soft delete: members are locked out, data is retained and restorable.</p>
              </div>
              <button className="btn alt" onClick={() => load(token)}>Refresh</button>
            </section>
            <section className="panel">
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th>Workspace</th><th>Slug</th><th>Members</th><th>Leads</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
                  <tbody>
                    {orgs.map((o) => (
                      <tr key={o.id}>
                        <td>{o.name}</td>
                        <td className="muted">{o.slug}</td>
                        <td>{o.member_count}</td>
                        <td>{o.lead_count}</td>
                        <td><span className="tag">{o.deleted_at ? "deleted" : o.is_active ? "active" : "suspended"}</span></td>
                        <td className="muted">{o.created_at ? o.created_at.slice(0, 10) : "—"}</td>
                        <td>
                          <div className="row">
                            {!o.deleted_at && o.is_active && <button className="btn alt" disabled={busy === o.id} onClick={() => ask(o, "suspend")}>Suspend</button>}
                            {(o.deleted_at || !o.is_active) && <button className="btn alt" disabled={busy === o.id} onClick={() => ask(o, "restore")}>Restore</button>}
                            {!o.deleted_at && <button className="btn alt" disabled={busy === o.id} onClick={() => ask(o, "delete")}>Delete</button>}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!orgs.length && <tr><td colSpan={7}>No workspaces found.</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
        {pending && (
          <section className="panel auth-panel">
            <span className="eyebrow">CONFIRM {pending.action.toUpperCase()}</span>
            <h1>{pending.action === "delete" ? `Delete "${pending.org.name}"?` : pending.action === "suspend" ? `Suspend "${pending.org.name}"?` : `Restore "${pending.org.name}"?`}</h1>
            <p className="muted">
              {pending.action === "delete"
                ? `Soft-delete: ${pending.org.member_count} member(s) are locked out immediately; ${pending.org.lead_count} lead(s) and all data are retained and restorable. Written to the audit log.`
                : pending.action === "suspend"
                ? `${pending.org.member_count} member(s) are locked out until you restore the workspace. Written to the audit log.`
                : "Members can sign in again immediately. Written to the audit log."}
            </p>
            <label>Reason (required, min 3 characters)
              <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="Why are you doing this?" autoFocus />
            </label>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn" disabled={busy === pending.org.id || reason.trim().length < 3} onClick={confirmAct}>
                {pending.action === "delete" ? "Yes, delete this workspace" : pending.action === "suspend" ? "Yes, suspend" : "Yes, restore"}
              </button>
              <button className="btn alt" onClick={() => setPending(null)}>Cancel</button>
            </div>
          </section>
        )}
        {note && <p className="alert" role="status">{note}</p>}
      </main>
    </>
  );
}
