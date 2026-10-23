import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../../api.js";
import { Card, Codes, DecisionBadge, ErrorBox, Loading, RiskBadge, StatusBadge } from "../../components/ui.jsx";
import { DOC_LABELS, conf, fmtDate, fmtDateTime } from "../../format.js";

const OFFICER_ACTIONS = [
  ["APPROVE", "Recommend approve"],
  ["REJECT", "Recommend reject"],
  ["REQUEST_RESUBMISSION", "Ask applicant to resubmit"],
];
const CHECKER_ACTIONS = [
  ["APPROVE", "Approve (final)"],
  ["REJECT", "Reject (final)"],
  ["SEND_BACK", "Send back to officer"],
];

function actionLabel(mode, action) {
  if (mode === "checker") return "Record final decision";
  return action === "REQUEST_RESUBMISSION" ? "Send back to applicant" : "Send to checker";
}

/** KYC Officer workbench (mode="officer") and Compliance checker view (mode="checker"). */
export default function Workbench({ mode }) {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [activeDoc, setActiveDoc] = useState(null);
  const [texts, setTexts] = useState({});
  const [editing, setEditing] = useState(null);
  const [decision, setDecision] = useState({ action: "APPROVE", comment: "" });
  const [notice, setNotice] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [editError, setEditError] = useState(null);
  const [actionNotice, setActionNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const { data: d } = await api.get(`/applications/${id}/review`);
      setData(d);
      setActiveDoc((cur) => cur ?? (d.documents.find((x) => x.selected_as) ?? d.documents[0])?.doc_id ?? null);
    } catch (err) {
      setError(err);
    }
  }
  useEffect(() => { load(); }, [id]);

  // Opening a document tab fetches its text; the server records every view in the audit trail.
  useEffect(() => {
    if (activeDoc && texts[activeDoc] === undefined) {
      api.get(`/documents/${activeDoc}/content`)
        .then((r) => setTexts((t) => ({ ...t, [activeDoc]: r.data.text })))
        .catch(setError);
    }
  }, [activeDoc]);

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  const app = data.application;
  const doc = data.documents.find((d) => d.doc_id === activeDoc);
  const canCorrect = mode === "officer" && app.status === "IN_REVIEW";
  const canAct = mode === "officer" ? app.status === "IN_REVIEW" : app.status === "PENDING_CHECKER";
  const triggered = data.rule_details.filter((r) => r.triggered);
  const skipped = data.rule_details.filter((r) => r.skipped);

  async function saveCorrection(e) {
    e.preventDefault();
    setEditError(null);
    if (editing.reason.trim().length < 10) {
      setEditError({ message: "Reason must be at least 10 characters", fields: [] });
      return;
    }
    setBusy(true);
    try {
      const { data: d } = await api.patch(`/applications/${id}/fields`, { ...editing, version: app.version });
      setData(d);
      setEditing(null);
      setNotice(`Corrected ${editing.field_name}. Rules re-ran: decision is now ${d.decision.decision}.`);
    } catch (err) {
      setEditError(err);
    } finally {
      setBusy(false);
    }
  }

  // Errors and results are shown next to the button, where the user is looking.
  async function act(e) {
    e.preventDefault();
    setActionError(null);
    setActionNotice(null);
    if (decision.comment.trim().length < 10) {
      setActionError({ message: "Comment must be at least 10 characters", fields: [] });
      return;
    }
    setBusy(true);
    try {
      const url = mode === "officer" ? `/applications/${id}/recommend` : `/applications/${id}/check`;
      const { data: r } = await api.post(url, { ...decision, version: app.version });
      const msg = `Done: application is now ${r.status}${r.account_no ? ` (account ${r.account_no})` : ""}.`;
      setNotice(msg);
      setActionNotice(msg);
      setDecision({ action: "APPROVE", comment: "" });
      await load();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <Card
        title={`${app.application_id} · ${app.full_name}`}
        actions={
          <span className="row">
            <StatusBadge status={app.status} />
            <Link className="btn" to={mode === "officer" ? "/review" : "/checker"}>Back to queue</Link>
            {mode === "checker" && <Link className="btn" to={`/audit/${app.application_id}`}>Audit trail</Link>}
          </span>
        }
      >
        <div className="facts">
          <div><span>Decision</span><DecisionBadge decision={data.decision.decision} /></div>
          <div><span>Reason codes</span><Codes codes={data.decision.reason_codes} /></div>
          <div><span>Name match</span><strong>{data.decision.name_match_score ?? "—"}</strong></div>
          <div><span>Risk</span><RiskBadge risk={data.decision.risk_category} /></div>
          <div><span>Re-KYC due</span>{fmtDate(data.decision.rekyc_due_date)}</div>
          <div><span>Rules run</span>#{data.decision.run_no} ({data.decision.trigger?.toLowerCase()})</div>
          <div><span>Occupation</span>{app.occupation_code}</div>
          <div><span>Income</span>₹{Number(app.annual_income).toLocaleString("en-IN")}</div>
        </div>
        {notice && <p className="alert alert-ok">{notice}</p>}
        <ErrorBox error={error} />
      </Card>

      <div className="grid-2 workbench">
        <Card title="Documents">
          <div className="tabs">
            {data.documents.map((d) => (
              <button key={d.doc_id} className={`tab ${d.doc_id === activeDoc ? "active" : ""} ${d.superseded ? "superseded" : ""}`}
                onClick={() => setActiveDoc(d.doc_id)}>
                {d.doc_ref}
                <span className="small">{DOC_LABELS[d.doc_type] ?? d.doc_type}{d.selected_as ? " ✓" : ""}</span>
              </button>
            ))}
          </div>
          {doc && (
            <>
              <p className="small">
                Declared <strong>{DOC_LABELS[doc.declared_doc_type]}</strong> · classified{" "}
                <strong className={doc.doc_type !== doc.declared_doc_type ? "text-danger" : ""}>{DOC_LABELS[doc.doc_type] ?? doc.doc_type}</strong>{" "}
                <span className={doc.doc_type_confidence < data.min_field_confidence ? "conf-low" : "muted"}>
                  (conf {conf(doc.doc_type_confidence)})
                </span>
                {doc.selected_as ? <> · used as <strong>{DOC_LABELS[doc.selected_as]}</strong></> : <span className="muted"> · not used by rules</span>}
              </p>
              <pre className="doc-text">{texts[doc.doc_id] ?? "Loading text…"}</pre>
            </>
          )}
        </Card>

        <div className="stack">
          <Card title="Declared vs documents">
            <table className="table compact">
              <thead><tr><th>Field</th><th>Declared</th><th>On documents</th></tr></thead>
              <tbody>
                {data.comparison.map((row) => (
                  <tr key={row.field}>
                    <td>{row.label}</td>
                    <td><code>{row.declared}</code></td>
                    <td>
                      {row.sources.length === 0 ? <span className="muted">—</span> : row.sources.map((s) => (
                        <div key={s.slot} className={!s.usable ? "conf-low" : s.matches ? "" : "mismatch"}>
                          <span className="muted small">{DOC_LABELS[s.slot]}:</span> <code>{s.value}</code>{" "}
                          <span className="small">({conf(s.confidence)}{!s.usable ? ", not used" : ""})</span>
                          {s.usable && (s.matches ? " ✓" : " ✗")}
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">Red = differs from the form · amber = below {data.min_field_confidence} confidence, ignored by identity rules.</p>
          </Card>

          {doc && (
            <Card title={`Extracted fields · ${doc.doc_ref}`}>
              <table className="table compact">
                <thead><tr><th>Field</th><th>Value</th><th>Conf.</th><th>Source</th>{canCorrect && <th />}</tr></thead>
                <tbody>
                  {[{ field_name: "doc_type", value: doc.doc_type, confidence: doc.doc_type_confidence,
                      usable: doc.doc_type_confidence >= data.min_field_confidence, source: doc.doc_type_source, previous: [] },
                    ...doc.fields].map((f) => (
                    <tr key={f.field_name} className={f.usable ? "" : "low-confidence"}>
                      <td>{f.field_name}</td>
                      <td>
                        <code>{f.value}</code>
                        {f.previous?.length > 0 && <div className="small muted">was {f.previous.map((p) => p.value).join(", ")}</div>}
                        {f.correction_reason && <div className="small muted">“{f.correction_reason}” — {f.corrected_by}</div>}
                      </td>
                      <td>{conf(f.confidence)}</td>
                      <td className="small">{f.source}</td>
                      {canCorrect && (
                        <td>
                          <button className="btn btn-small" onClick={() => setEditing({
                            doc_id: doc.doc_id, field_name: f.field_name, value: f.value, reason: "" })}>Correct</button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              {editing && editing.doc_id === doc.doc_id && (
                <form className="inline-form" onSubmit={saveCorrection}>
                  <strong>Correct {editing.field_name}</strong>
                  <input value={editing.value} onChange={(e) => setEditing({ ...editing, value: e.target.value })} />
                  <input placeholder="Reason (min 10 characters)" value={editing.reason}
                    onChange={(e) => setEditing({ ...editing, reason: e.target.value })} />
                  <span className="row">
                    <button className="btn btn-primary" disabled={busy}>Save and re-run rules</button>
                    <button type="button" className="btn" onClick={() => { setEditing(null); setEditError(null); }}>Cancel</button>
                  </span>
                  <ErrorBox error={editError} />
                </form>
              )}
            </Card>
          )}

          <Card title="Rule results">
            {triggered.length === 0 ? <p className="alert alert-ok">All rules passed.</p> : triggered.map((r) => (
              <details key={r.rule} className={`rule rule-${r.outcome.toLowerCase()}`}>
                <summary><strong>{r.rule}</strong> {r.code} <span className="small">→ {r.outcome}</span></summary>
                <pre className="small">{JSON.stringify(r.compared, null, 2)}</pre>
              </details>
            ))}
            <p className="muted small">{data.rule_details.length - triggered.length - skipped.length} passed · {skipped.length} skipped (field not usable):{" "}
              {skipped.map((r) => r.rule).join(", ") || "none"}</p>
          </Card>

          {data.screening.length > 0 && (
            <Card title="Watchlist screening">
              {data.screening.map((h) => (
                <div key={h.entry_id} className={`alert ${h.result === "MATCH" ? "alert-danger" : "alert-warn"}`}>
                  <strong>{h.list_type} {h.result}</strong> · entry <code>{h.entry_id}</code> {h.entry_name}<br />
                  Similarity <strong>{h.similarity.toFixed(4)}</strong> on {h.matched_on.toLowerCase()} · DOB{" "}
                  applicant {h.applicant_dob} vs list {h.list_dob || "(empty)"} → {h.dob_comparison}
                </div>
              ))}
            </Card>
          )}

          <Card title="Recommendations">
            {data.recommendations.length === 0 ? <p className="muted">None yet.</p> : (
              <ul className="history">
                {data.recommendations.map((r, i) => (
                  <li key={i}><strong>{r.action}</strong> by {r.user_name} ({r.role}) · {fmtDateTime(r.created_at)}<br />“{r.comment}”</li>
                ))}
              </ul>
            )}
            {canAct ? (
              <form className="inline-form" onSubmit={act}>
                {(mode === "officer" ? OFFICER_ACTIONS : CHECKER_ACTIONS).map(([value, label]) => (
                  <label key={value} className="radio">
                    <input type="radio" name="action" value={value} checked={decision.action === value}
                      onChange={() => setDecision({ ...decision, action: value })} /> {label}
                  </label>
                ))}
                <textarea rows={2} placeholder="Comment (min 10 characters)" value={decision.comment}
                  onChange={(e) => setDecision({ ...decision, comment: e.target.value })} />
                <button className="btn btn-primary" disabled={busy}>{actionLabel(mode, decision.action)}</button>
                {mode === "officer" && decision.action === "REQUEST_RESUBMISSION" && (
                  <p className="muted small">This goes back to the applicant (not to the checker) with a 7-day deadline.</p>
                )}
                <ErrorBox error={actionError} />
                {mode === "checker" && app.maker_id && <p className="muted small">Maker: {app.maker_id} ({app.maker_action}). You must be a different user.</p>}
              </form>
            ) : (
              <>
                {actionNotice && <p className="alert alert-ok">{actionNotice}</p>}
                <p className="muted small">No action available in status {app.status}.</p>
              </>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
