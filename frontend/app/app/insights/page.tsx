"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "../../lib/api";

type Score = { lead_id: number; name: string; phone: string; status: string; score: number; factors: string[] };
type Forecast = { scope: string; open_deals: number; total_amount: number; weighted_total: number;
  by_month: { month: string; deals: number; amount: number; weighted: number }[];
  unscheduled: { deals: number; amount: number; weighted: number }; method: string };
type Action = { type: string; ref: string; label: string; reason: string };
type Digest = { lead_id: number; name: string; status: string; source: string;
  days_since_last_touch: number | null; activity_count: number; activity_by_kind: Record<string, number>;
  latest: { kind: string; body: string; created_at: string | null }[];
  open_tasks: { id: number; title: string; due_at: string | null }[]; method: string };

const ACTION_LABELS: Record<string, string> = {
  overdue_task: "Overdue task", deal_past_close: "Deal past close", deal_stale: "Deal stale",
  hot_lead_no_task: "Hot lead, no task", lead_idle: "Lead idle",
};

export default function InsightsPage() {
  const [scores, setScores] = useState<Score[]>([]);
  const [scoreMethod, setScoreMethod] = useState("");
  const [fc, setFc] = useState<Forecast | null>(null);
  const [actions, setActions] = useState<Action[]>([]);
  const [actionsMethod, setActionsMethod] = useState("");
  const [digest, setDigest] = useState<Digest | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    apiFetch("/insights/lead-scores").then((d) => { setScores(d.scores); setScoreMethod(d.method); })
      .catch((e) => setNote(e.message));
    apiFetch("/insights/forecast").then(setFc).catch(() => {});
    apiFetch("/insights/next-actions").then((d) => { setActions(d.actions); setActionsMethod(d.method); }).catch(() => {});
  }, []);

  async function openDigest(leadId: number) {
    try { setDigest(await apiFetch(`/insights/lead-digest/${leadId}`)); }
    catch (err) { setNote(err instanceof Error ? err.message : "Digest failed"); }
  }

  const money = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">Workspace</span><h1 style={{ margin: "6px 0" }}>Insights</h1></div>
      </div>
      <p className="muted">Next best actions, lead scoring and pipeline forecast, computed from your live data. How each number is produced is shown with it.</p>
      {note && <p className="alert" role="status">{note}</p>}

      <div className="panel" style={{ margin: 0 }}>
        <h2 style={{ marginTop: 0 }}>Next best actions</h2>
        {actions.length > 0 && (
          <div className="timeline">
            {actions.map((a, i) => (
              <div className="ev" key={i}>
                <span className="tag">{ACTION_LABELS[a.type] || a.type}</span> <strong>{a.label}</strong>
                <small>{a.reason}</small>
              </div>
            ))}
          </div>
        )}
        {!actions.length && <p className="muted">Nothing needs attention right now: no overdue tasks, no idle hot leads, no deals at risk.</p>}
        <small className="muted">Method: {actionsMethod}</small>
      </div>

      <div className="panel" style={{ margin: 0 }}>
        <h2 style={{ marginTop: 0 }}>Pipeline forecast</h2>
        {fc && (
          <>
            <p>
              <strong>{fc.open_deals}</strong> open deal(s), total <strong>{money(fc.total_amount)} EGP</strong>,
              probability-weighted <strong>{money(fc.weighted_total)} EGP</strong>
              {fc.scope === "own" && " (your deals only)"}.
            </p>
            {fc.by_month.length > 0 && (
              <table>
                <thead><tr><th>Expected close</th><th>Deals</th><th>Amount</th><th>Weighted</th></tr></thead>
                <tbody>
                  {fc.by_month.map((m) => (
                    <tr key={m.month}><td>{m.month}</td><td>{m.deals}</td><td>{money(m.amount)}</td><td>{money(m.weighted)}</td></tr>
                  ))}
                  {fc.unscheduled.deals > 0 && (
                    <tr><td>No close date</td><td>{fc.unscheduled.deals}</td><td>{money(fc.unscheduled.amount)}</td><td>{money(fc.unscheduled.weighted)}</td></tr>
                  )}
                </tbody>
              </table>
            )}
            {fc.by_month.length === 0 && fc.unscheduled.deals === 0 && <p className="muted">No open deals yet. The forecast fills in as deals are added to the pipeline.</p>}
            <small className="muted">Method: {fc.method}</small>
          </>
        )}
      </div>

      <div className="panel" style={{ margin: 0 }}>
        <h2 style={{ marginTop: 0 }}>Lead scoring</h2>
        <p className="muted">Click a lead to see its conversation digest.</p>
        {scores.length > 0 && (
          <table>
            <thead><tr><th>Lead</th><th>Status</th><th>Score</th><th>Why</th></tr></thead>
            <tbody>
              {scores.map((s) => (
                <tr key={s.lead_id} onClick={() => openDigest(s.lead_id)} style={{ cursor: "pointer" }}>
                  <td>{s.name}</td>
                  <td><span className="tag">{s.status.replace(/_/g, " ")}</span></td>
                  <td><strong>{s.score}</strong>/100</td>
                  <td><small className="muted">{s.factors.join(" · ")}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!scores.length && <p className="muted">No active leads to score yet.</p>}
        <small className="muted">Method: {scoreMethod}</small>
      </div>

      {digest && (
        <div className="panel" style={{ margin: 0 }}>
          <h2 style={{ marginTop: 0 }}>Conversation digest: {digest.name}</h2>
          <p>
            Status <span className="tag">{digest.status.replace(/_/g, " ")}</span> · {digest.activity_count} logged activit{digest.activity_count === 1 ? "y" : "ies"}
            {digest.days_since_last_touch !== null
              ? ` · last touch ${digest.days_since_last_touch === 0 ? "today" : digest.days_since_last_touch + " day(s) ago"}`
              : " · no logged activity yet"}
          </p>
          {Object.keys(digest.activity_by_kind).length > 0 && (
            <p className="muted">By kind: {Object.entries(digest.activity_by_kind).map(([k, v]) => `${k} (${v})`).join(", ")}</p>
          )}
          {digest.latest.length > 0 && (
            <div className="timeline">
              {digest.latest.map((a, i) => (
                <div className="ev" key={i}><span className="tag">{a.kind}</span> {a.body}<small>{a.created_at ? a.created_at.slice(0, 16).replace("T", " ") : ""}</small></div>
              ))}
            </div>
          )}
          {digest.open_tasks.length > 0 && (
            <p>Open tasks: {digest.open_tasks.map((t) => t.title + (t.due_at ? ` (due ${t.due_at.slice(0, 10)})` : "")).join(" · ")}</p>
          )}
          <small className="muted">Method: {digest.method}</small>
        </div>
      )}
    </>
  );
}
