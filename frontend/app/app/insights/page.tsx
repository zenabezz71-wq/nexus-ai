"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "../../lib/api";

type Score = { lead_id: number; name: string; phone: string; status: string; score: number; factors: string[] };
type Forecast = { scope: string; open_deals: number; total_amount: number; weighted_total: number;
  by_month: { month: string; deals: number; amount: number; weighted: number }[];
  unscheduled: { deals: number; amount: number; weighted: number }; method: string };

export default function InsightsPage() {
  const [scores, setScores] = useState<Score[]>([]);
  const [scoreMethod, setScoreMethod] = useState("");
  const [fc, setFc] = useState<Forecast | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    apiFetch("/insights/lead-scores").then((d) => { setScores(d.scores); setScoreMethod(d.method); })
      .catch((e) => setNote(e.message));
    apiFetch("/insights/forecast").then(setFc).catch(() => {});
  }, []);

  const money = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });

  return (
    <>
      <div className="workspace-heading">
        <div><span className="eyebrow">Workspace</span><h1 style={{ margin: "6px 0" }}>Insights</h1></div>
      </div>
      <p className="muted">Lead scoring and pipeline forecast, computed from your live data. How each number is produced is shown with it.</p>
      {note && <p className="alert" role="status">{note}</p>}

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
        {scores.length > 0 && (
          <table>
            <thead><tr><th>Lead</th><th>Status</th><th>Score</th><th>Why</th></tr></thead>
            <tbody>
              {scores.map((s) => (
                <tr key={s.lead_id}>
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
    </>
  );
}
