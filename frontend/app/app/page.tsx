"use client";
import { useEffect, useState } from "react";
import { apiFetch, fmtDateTime } from "../lib/api";

type RiskDeal = { id: number; title: string; amount: number | null; currency: string; expected_close: string | null; last_activity_at: string | null };
type DashTask = { id: number; title: string; due_at: string };
type TeamRow = { user_id: number; name: string; deals_won: number; open_deals: number; activities: number };
type Dash = {
  period: string; scope: string;
  total_leads: number; new_leads_period: number; new_leads_change_pct: number | null;
  active_deals: number; pipeline_value: number;
  revenue_period: number; revenue_change_pct: number | null; deals_won_period: number;
  expected_revenue: number; conversion_rate_pct: number | null; conversion_note: string;
  top_lead_sources: { source: string; leads: number }[];
  deals_at_risk: RiskDeal[];
  tasks_due_today: DashTask[]; tasks_overdue: DashTask[]; tasks_overdue_count: number;
  team: TeamRow[]; insights: string[]; insights_method: string;
};

const PERIODS = [
  { key: "day", label: "Today" },
  { key: "week", label: "7 days" },
  { key: "month", label: "30 days" },
];

function Change({ pct }: { pct: number | null }) {
  if (pct == null) return null;
  const up = pct >= 0;
  return <small className="muted" style={{ color: up ? "#16a34a" : "#dc2626" }}> {up ? "▲" : "▼"} {Math.abs(pct)}% vs previous</small>;
}

function money(v: number) {
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export default function DashboardPage() {
  const [period, setPeriod] = useState("week");
  const [d, setD] = useState<Dash | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    setNote("");
    apiFetch("/dashboard/executive?period=" + period).then(setD).catch((e) => setNote(e.message));
  }, [period]);

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">NEXUS</span><h1 style={{ margin: "6px 0" }}>Executive Dashboard</h1></div>
        <div className="row">
          {PERIODS.map((p) => (
            <button key={p.key} type="button" className={"btn " + (period === p.key ? "" : "alt")} onClick={() => setPeriod(p.key)}>{p.label}</button>
          ))}
        </div>
      </div>
      <p className="muted">The state of the company at a glance{d?.scope === "own" ? " (your own records)" : ""}. Every number is computed live from workspace data.</p>
      {note && <p className="alert" role="status">{note}</p>}
      {!d && !note && <p className="muted">Loading…</p>}
      {d && (
        <>
          <div className="kpi-grid">
            <div className="panel kpi"><small className="muted">Total leads</small><strong>{d.total_leads}</strong><small className="muted">+{d.new_leads_period} this period<Change pct={d.new_leads_change_pct} /></small></div>
            <div className="panel kpi"><small className="muted">Active deals</small><strong>{d.active_deals}</strong><small className="muted">EGP {money(d.pipeline_value)} in pipeline</small></div>
            <div className="panel kpi"><small className="muted">Revenue (won)</small><strong>EGP {money(d.revenue_period)}</strong><small className="muted">{d.deals_won_period} deal(s) won<Change pct={d.revenue_change_pct} /></small></div>
            <div className="panel kpi"><small className="muted">Expected revenue</small><strong>EGP {money(d.expected_revenue)}</strong><small className="muted">probability-weighted open deals</small></div>
            <div className="panel kpi"><small className="muted">Conversion rate</small><strong>{d.conversion_rate_pct == null ? "—" : d.conversion_rate_pct + "%"}</strong><small className="muted">{d.conversion_note}</small></div>
          </div>

          <div className="panel" style={{ borderColor: "var(--accent)" }}>
            <span className="eyebrow">NEXUS Intelligence</span>
            <ul style={{ margin: "8px 0", paddingLeft: 18 }}>
              {d.insights.map((s, i) => <li key={i} style={{ marginBottom: 4 }}>{s}</li>)}
            </ul>
            <small className="muted">{d.insights_method}</small>
          </div>

          <div className="dash-cols">
            <div className="panel" style={{ margin: 0 }}>
              <h3 style={{ marginTop: 0 }}>Deals at risk ({d.deals_at_risk.length})</h3>
              {d.deals_at_risk.map((x) => (
                <div key={x.id} className="ev">
                  {x.title} {x.amount != null && <span className="muted">· {x.currency} {money(x.amount)}</span>}
                  <small>
                    {x.expected_close ? "expected close " + x.expected_close + " · " : ""}
                    {x.last_activity_at ? "last activity " + fmtDateTime(x.last_activity_at) : "no recorded activity"}
                  </small>
                </div>
              ))}
              {!d.deals_at_risk.length && <p className="muted">No open deals look stale or past their expected close.</p>}
            </div>
            <div className="panel" style={{ margin: 0 }}>
              <h3 style={{ marginTop: 0 }}>Tasks</h3>
              <h4 style={{ margin: "4px 0" }}>Due today ({d.tasks_due_today.length})</h4>
              {d.tasks_due_today.map((t) => <div key={t.id} className="ev">{t.title}<small>{fmtDateTime(t.due_at)}</small></div>)}
              {!d.tasks_due_today.length && <p className="muted">Nothing due today.</p>}
              <h4 style={{ margin: "12px 0 4px" }}>Overdue ({d.tasks_overdue_count})</h4>
              {d.tasks_overdue.map((t) => <div key={t.id} className="ev">{t.title}<small>due {fmtDateTime(t.due_at)}</small></div>)}
              {!d.tasks_overdue.length && <p className="muted">No overdue tasks.</p>}
            </div>
          </div>

          {d.team.length > 0 && (
            <div className="panel">
              <h3 style={{ marginTop: 0 }}>Team performance (this period)</h3>
              <table>
                <thead><tr><th>Member</th><th>Deals won</th><th>Open deals</th><th>Activities logged</th></tr></thead>
                <tbody>
                  {d.team.map((t) => (
                    <tr key={t.user_id}><td>{t.name}</td><td>{t.deals_won}</td><td>{t.open_deals}</td><td>{t.activities}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {d.top_lead_sources.length > 0 && (
            <div className="panel">
              <h3 style={{ marginTop: 0 }}>Top lead sources</h3>
              {d.top_lead_sources.map((s) => (
                <div key={s.source} className="ev">{s.source}<small>{s.leads} lead(s)</small></div>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
