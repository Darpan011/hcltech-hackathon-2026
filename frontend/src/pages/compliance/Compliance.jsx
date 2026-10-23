import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api, { downloadFile } from "../../api.js";
import { Card, ErrorBox, Loading } from "../../components/ui.jsx";
import { STATUS_LABELS, fmtDateTime, pct } from "../../format.js";

export function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [range, setRange] = useState({ from: "", to: "" });

  const load = () => {
    const params = {};
    if (range.from) params.from = range.from;
    if (range.to) params.to = range.to;
    api.get("/dashboard", { params }).then((r) => setData(r.data)).catch(setError);
  };
  useEffect(load, []);

  const statusData = data ? Object.entries(data.by_status).map(([k, v]) => ({ status: STATUS_LABELS[k] ?? k, count: v })) : [];
  const tiles = data ? [
    ["Applications", data.total_applications],
    ["Straight-through", pct(data.straight_through_rate)],
    ["Review rate", pct(data.review_rate)],
    ["Reject rate", pct(data.reject_rate)],
    ["Pending checker", `${data.pending_checker}${data.pending_checker_overdue ? ` (${data.pending_checker_overdue} overdue)` : ""}`],
    ["Accounts opened", data.accounts_opened],
    ["Avg time in review", data.avg_time_in_review_minutes == null ? "—" : `${data.avg_time_in_review_minutes} min`],
  ] : [];

  return (
    <div className="stack">
      <Card title="Compliance dashboard" actions={
        <form className="row" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <label className="small">From <input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></label>
          <label className="small">To <input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></label>
          <button className="btn">Apply</button>
        </form>
      }>
        <ErrorBox error={error} />
        {!data ? <Loading /> : (
          <div className="tiles">
            {tiles.map(([label, value]) => (
              <div className="tile" key={label}><span>{label}</span><strong>{value}</strong></div>
            ))}
          </div>
        )}
        <p className="muted small">Rates use the first (automatic) rules run of each application.</p>
      </Card>
      {data && (
        <div className="grid-2">
          <Card title="Applications by status">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={statusData} margin={{ left: 0, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="status" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="Top 5 reason codes">
            <table className="table compact">
              <tbody>
                {data.top_reason_codes.map((r) => (
                  <tr key={r.code}><td><code>{r.code}</code></td><td className="num">{r.count}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
}

export function AuditTrail() {
  const { id } = useParams();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get(`/applications/${id}/audit`).then((r) => setRows(r.data)).catch(setError); }, [id]);

  return (
    <Card title={`Audit trail · ${id}`} actions={
      <span className="row">
        <Link className="btn" to={`/checker/${id}`}>Open case</Link>
        <button className="btn" onClick={() => downloadFile(`/applications/${id}/audit/export`, `audit_${id}.csv`).catch(setError)}>Export CSV</button>
      </span>
    }>
      <p className="muted small">Append-only: the database rejects any update or delete of these rows.</p>
      <ErrorBox error={error} />
      {!rows ? <Loading /> : (
        <table className="table compact audit">
          <thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Status</th><th>Details</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td className="small">{fmtDateTime(r.ts)}</td>
                <td className="small">{r.actor_id}<br /><span className="muted">{r.actor_role}</span></td>
                <td><code>{r.action}</code><div className="small muted">{r.entity} {r.entity_id.slice(0, 8)}</div></td>
                <td className="small">{r.from_status || r.to_status ? `${r.from_status ?? "—"} → ${r.to_status ?? "—"}` : ""}</td>
                <td className="small">
                  {r.before && <div>before: <code>{JSON.stringify(r.before)}</code></div>}
                  {r.after && <div>after: <code>{JSON.stringify(r.after)}</code></div>}
                  {r.comment && <div>“{r.comment}”</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export function ConfigPage() {
  const [rows, setRows] = useState(null);
  const [edits, setEdits] = useState({});
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const load = () => api.get("/config").then((r) => setRows(r.data)).catch(setError);
  useEffect(() => { load(); }, []);

  async function save(key, original) {
    setError(null);
    setNotice(null);
    try {
      let value = edits[key];
      if (typeof original === "number") value = Number(value);
      else value = JSON.parse(value);
      await api.put(`/config/${key}`, { value });
      setNotice(`Saved ${key}. It applies to the next rules run.`);
      setEdits((e) => { const n = { ...e }; delete n[key]; return n; });
      load();
    } catch (err) {
      setError(err.message ? err : { message: "Value must be valid JSON" });
    }
  }

  return (
    <Card title="Rules configuration">
      <p className="muted small">Thresholds live in the database, not in code. Every change is audited.</p>
      <ErrorBox error={error} />
      {notice && <p className="alert alert-ok">{notice}</p>}
      {!rows ? <Loading /> : (
        <table className="table compact">
          <thead><tr><th>Key</th><th>Value</th><th>Updated</th><th /></tr></thead>
          <tbody>
            {rows.map(({ key, value, updated_at }) => {
              const text = edits[key] ?? (typeof value === "number" ? String(value) : JSON.stringify(value));
              return (
                <tr key={key}>
                  <td><code>{key}</code></td>
                  <td><input className="mono" value={text} onChange={(e) => setEdits({ ...edits, [key]: e.target.value })} /></td>
                  <td className="small">{fmtDateTime(updated_at)}</td>
                  <td>{edits[key] !== undefined && <button className="btn btn-small btn-primary" onClick={() => save(key, value)}>Save</button>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}
