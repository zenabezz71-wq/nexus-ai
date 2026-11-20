"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Member = {
  membership_id: number;
  user_id: number;
  name: string;
  email: string;
  role: string;
  grants: string[];
  permissions: string[];
};
type Me = { name: string; organization_name: string; role: string; permissions?: string[] };

const ROLES = ["owner", "admin", "manager", "sales"] as const;
const GRANTABLE: { key: string; label: string; hint: string }[] = [
  { key: "leads.view_all", label: "View all leads", hint: "See every lead, not only assigned ones" },
  { key: "contacts.view_all", label: "View all contacts", hint: "See every contact in the workspace" },
  { key: "contacts.export", label: "Export contacts", hint: "Download contact data" },
  { key: "deals.delete", label: "Delete deals", hint: "Remove deals from the pipeline" },
  { key: "reports.company", label: "Company reports", hint: "See company-wide analytics" },
  { key: "revenue.view", label: "View revenue", hint: "See revenue figures" },
  { key: "integrations.manage", label: "Manage integrations", hint: "Connect and disconnect tools" },
  { key: "billing.manage", label: "Manage billing", hint: "Owner only to grant" },
];

export default function TeamPage() {
  const [token, setToken] = useState("");
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [note, setNote] = useState("Loading your workspace team...");
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
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
    return typeof d.detail === "string" ? d.detail : Array.isArray(d.detail) ? d.detail.map((x) => x.msg).join(". ") : "Request failed. Please try again.";
  }
  async function req(path: string, init: RequestInit = {}) {
    const r = await fetch(API + path, { ...init, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init.headers || {}) } });
    const d = await r.json().catch(() => ({}));
    if (r.status === 404) { setUnavailable(true); throw Error("rollout"); }
    if (!r.ok) throw Error(errorText(d));
    return d;
  }

  async function load(t: string) {
    try {
      const r = await fetch(API + "/auth/me", { headers: { Authorization: `Bearer ${t}` } });
      if (r.status === 401) { localStorage.removeItem("nexus_token"); setNote("Please sign in again from the main page."); return; }
      const m = await r.json();
      setMe(m);
      const perms: string[] = m.permissions || [];
      const legacyCanView = !m.permissions && ["owner", "admin"].includes(m.role);
      if (!perms.includes("team.view") && !legacyCanView) { setNote("Your role does not include team management."); return; }
      const r2 = await fetch(API + "/team/members", { headers: { Authorization: `Bearer ${t}` } });
      if (r2.status === 404) { setUnavailable(true); return; }
      if (!r2.ok) { const d = await r2.json().catch(() => ({})); throw Error(errorText(d)); }
      setMembers(await r2.json());
      setNote("");
    } catch (e) {
      setNote((prev) => (prev === "" ? prev : e instanceof Error ? e.message : "Could not load the team."));
    }
  }

  useEffect(() => {
    const t = localStorage.getItem("nexus_token");
    if (!t) { setNote("Sign in from the main page first, then come back to manage your team."); return; }
    setToken(t);
    load(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const myPerms = me?.permissions || [];
  const legacyManage = !me?.permissions && ["owner", "admin"].includes(me?.role || "");
  const canManage = myPerms.includes("team.manage") || legacyManage;

  async function changeRole(m: Member, role: string) {
    if (role === m.role) return;
    setBusy(m.membership_id);
    try {
      const updated = await req(`/team/members/${m.membership_id}`, { method: "PATCH", body: JSON.stringify({ role }) });
      setMembers(members.map((x) => (x.membership_id === m.membership_id ? updated : x)));
      setNote(`${m.name} is now ${role}.`);
    } catch (e) { setNote(e instanceof Error && e.message !== "rollout" ? e.message : "Role change failed"); }
    finally { setBusy(null); }
  }

  async function toggleGrant(m: Member, key: string) {
    const grants = m.grants.includes(key) ? m.grants.filter((g) => g !== key) : [...m.grants, key];
    setBusy(m.membership_id);
    try {
      const updated = await req(`/team/members/${m.membership_id}/grants`, { method: "PUT", body: JSON.stringify({ grants }) });
      setMembers(members.map((x) => (x.membership_id === m.membership_id ? updated : x)));
      setNote(`Updated extra permissions for ${m.name}.`);
    } catch (e) { setNote(e instanceof Error && e.message !== "rollout" ? e.message : "Grant update failed"); }
    finally { setBusy(null); }
  }

  return (
    <>
      <header className="top">
        <div>
          <div className="brand"><span className="mark">✦</span> NEXUS AI</div>
          <div className="muted">Team management</div>
        </div>
        <div className="row">
          <a className="btn alt" href="/">Workspace</a>
          <button className="btn alt" type="button" onClick={toggleTheme}>{theme === "dark" ? "☀ Light" : "🌙 Dark"}</button>
        </div>
      </header>
      <main className="shell">
        {unavailable ? (
          <section className="panel auth-panel">
            <span className="eyebrow">COMING SOON</span>
            <h1>Team management is being rolled out.</h1>
            <p className="muted">The API update that powers this page is deploying next. Check back shortly; nothing about your workspace changes.</p>
            <a className="btn alt" href="/">Back to my workspace</a>
          </section>
        ) : !me ? (
          <section className="panel auth-panel"><h1>Loading...</h1></section>
        ) : (
          <>
            <section className="panel workspace-heading">
              <div>
                <span className="eyebrow">WORKSPACE TEAM</span>
                <h1>{me.organization_name}</h1>
                <p className="muted">{me.name} · {me.role} · Roles and extra permissions follow the workspace access matrix.</p>
              </div>
            </section>
            {!canManage && (
              <section className="panel">
                <p className="muted">You can see the team, but only owners and admins can change roles or extra permissions.</p>
              </section>
            )}
            {members.map((m) => (
              <section className="panel" key={m.membership_id}>
                <div className="workspace-heading">
                  <div>
                    <h2 style={{ margin: "0 0 6px" }}>{m.name} <span className="tag">{m.role}</span></h2>
                    <p className="muted" style={{ margin: 0 }}>{m.email}</p>
                  </div>
                  {canManage && (
                    <div className="row">
                      <label className="muted" htmlFor={`role-${m.membership_id}`}>Role</label>
                      <select
                        id={`role-${m.membership_id}`}
                        value={m.role}
                        disabled={busy === m.membership_id}
                        onChange={(e) => changeRole(m, e.target.value)}
                      >
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </div>
                  )}
                </div>
                <h3 style={{ marginBottom: 8 }}>Extra permissions</h3>
                <p className="muted">Added on top of the {m.role} role. The API enforces every change; this page only reflects it.</p>
                <div className="crm-grid">
                  {GRANTABLE.map((g) => {
                    const on = m.grants.includes(g.key);
                    return (
                      <label key={g.key} className="row" style={{ gap: 8 }} title={g.hint}>
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={!canManage || busy === m.membership_id}
                          onChange={() => toggleGrant(m, g.key)}
                          style={{ width: "auto" }}
                        />
                        <span>{g.label}</span>
                      </label>
                    );
                  })}
                </div>
                <p className="muted" style={{ marginTop: 12 }}>Effective permissions: {m.permissions.join(", ")}</p>
              </section>
            ))}
            {!members.length && <section className="panel"><p className="muted">No members found.</p></section>}
          </>
        )}
        {note && <p className="alert" role="status">{note}</p>}
      </main>
    </>
  );
}
