import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../../api.js";
import { Card, Codes, ErrorBox, Loading, RiskBadge } from "../../components/ui.jsx";
import { fmtDateTime } from "../../format.js";

export function ReviewQueue() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get("/review/queue").then((r) => setRows(r.data)).catch(setError); }, []);

  return (
    <Card title={`Review queue${rows ? ` (${rows.length})` : ""}`}>
      <p className="muted small">HIGH risk first, then oldest submission first.</p>
      <ErrorBox error={error} />
      {!rows ? <Loading /> : rows.length === 0 ? <p className="muted">Nothing to review.</p> : (
        <table className="table">
          <thead><tr><th>Application</th><th>Name</th><th>PAN</th><th>Risk</th><th>Why it is here</th><th>Submitted</th></tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.application_id}>
                <td><Link to={`/review/${a.application_id}`}>{a.application_id}</Link></td>
                <td>{a.full_name}</td>
                <td><code>{a.pan_masked}</code></td>
                <td><RiskBadge risk={a.risk_category} /></td>
                <td><Codes codes={a.reason_codes} /></td>
                <td className="small">{fmtDateTime(a.submitted_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export function CheckerQueue() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get("/checker/queue").then((r) => setRows(r.data)).catch(setError); }, []);

  return (
    <Card title={`Checker queue${rows ? ` (${rows.length})` : ""}`}>
      <p className="muted small">Every reviewed case and every HIGH-risk approval needs a second person.</p>
      <ErrorBox error={error} />
      {!rows ? <Loading /> : rows.length === 0 ? <p className="muted">Nothing waiting.</p> : (
        <table className="table">
          <thead><tr><th>Application</th><th>Name</th><th>Risk</th><th>Route</th><th>Maker recommendation</th><th>Waiting</th></tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.application_id}>
                <td><Link to={`/checker/${a.application_id}`}>{a.application_id}</Link></td>
                <td>{a.full_name}</td>
                <td><RiskBadge risk={a.risk_category} /></td>
                <td className="small">{a.route === "HIGH_RISK_APPROVAL" ? "High-risk auto-approval" : "Officer recommendation"}</td>
                <td className="small">{a.maker_action ? <><strong>{a.maker_action}</strong> by {a.maker_name}<br />“{a.maker_comment}”</> : "—"}</td>
                <td className={a.sla_overdue ? "text-danger" : "small"}>{a.pending_hours} h{a.sla_overdue ? " · SLA breached" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
