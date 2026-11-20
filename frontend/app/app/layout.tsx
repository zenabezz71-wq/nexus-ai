"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, Me } from "../lib/api";

const LINKS = [
  { href: "/app/contacts", label: "Contacts" },
  { href: "/app/pipeline", label: "Pipeline" },
  { href: "/app/tasks", label: "Tasks" },
  { href: "/app/activity", label: "Activity" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const pathname = usePathname();

  useEffect(() => {
    const saved = localStorage.getItem("nexus_theme");
    const t = saved === "light" ? "light" : "dark";
    setTheme(t);
    document.documentElement.dataset.theme = t;
    if (!localStorage.getItem("nexus_token")) {
      window.location.replace("/");
      return;
    }
    apiFetch("/auth/me").then(setMe).catch(() => {});
  }, []);

  function toggleTheme() {
    const t = theme === "dark" ? "light" : "dark";
    setTheme(t);
    document.documentElement.dataset.theme = t;
    localStorage.setItem("nexus_theme", t);
  }
  function signOut() {
    localStorage.removeItem("nexus_token");
    window.location.replace("/");
  }

  const perms = me?.permissions || [];
  const canTeam = me ? (me.permissions ? perms.includes("team.view") : ["owner", "admin"].includes(me.role)) : false;

  return (
    <div className="app">
      <aside className="side">
        <div className="brand"><span className="mark">✦</span> NEXUS AI</div>
        <div className="org">{me ? me.organization_name : "Loading workspace..."}</div>
        <Link className="nav" href="/">Dashboard</Link>
        {LINKS.map((l) => (
          <Link key={l.href} className={"nav" + (pathname.startsWith(l.href) ? " active" : "")} href={l.href}>
            {l.label}
          </Link>
        ))}
        {canTeam && <Link className="nav" href="/team">Team</Link>}
        {me?.is_platform_admin && <Link className="nav" href="/platform">Platform</Link>}
        <div className="spacer" />
        {me && <div className="org" style={{ marginBottom: 8 }}>{me.name} · {me.role}</div>}
        <button className="btn alt mini" type="button" onClick={toggleTheme}>{theme === "dark" ? "☀ Light" : "🌙 Dark"}</button>
        <button className="btn alt mini" type="button" style={{ marginTop: 6 }} onClick={signOut}>Sign out</button>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
