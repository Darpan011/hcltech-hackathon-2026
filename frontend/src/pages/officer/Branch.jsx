import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import api from "../../api.js";
import { Card, Codes, DecisionBadge, ErrorBox, Loading, StatusBadge } from "../../components/ui.jsx";
import { DOC_LABELS, DOC_TYPES, fmtDate, fmtDateTime } from "../../format.js";

/** Officer's list of walk-in customers they entered at the branch. */
export function BranchIntake() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.get("/branch/applications").then((r) => setRows(r.data)).catch(setError); }, []);

  return (
    <Card title="Branch intake" actions={<Link className="btn btn-primary" to="/branch/new">New walk-in customer</Link>}>
      <p className="muted small">Customers bring their documents to the branch. You enter their details and documents;
        the system creates their login. Another KYC Officer reviews any case that needs review.</p>
      <ErrorBox error={error} />
      {!rows ? <Loading /> : rows.length === 0 ? <p className="muted">No customers entered yet.</p> : (
        <table className="table">
          <thead><tr><th>Application</th><th>Customer</th><th>Status</th><th>Reason codes</th><th>Entered</th></tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.application_id}>
                <td><Link to={`/branch/${a.application_id}`}>{a.application_id}</Link></td>
                <td>{a.full_name}</td>
                <td><StatusBadge status={a.status} /></td>
                <td><Codes codes={a.reason_codes} /></td>
                <td className="small">{fmtDate(a.application_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

/** Upload the customer's documents at the branch, submit, and see the result. */
export function BranchApplication() {
  const { id } = useParams();
  const location = useLocation();
  const [customer] = useState(location.state?.customer ?? null);   // one-time password: shown once only
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("PAN_CARD");
  const [busy, setBusy] = useState(false);

  const load = () => api.get(`/branch/applications/${id}`).then((r) => setData(r.data)).catch(setError);
  useEffect(() => {
    load();
    window.history.replaceState({}, "");     // drop the password from browser history state
  }, [id]);

  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("declared_doc_type", docType);
      const { data: d } = await api.post(`/branch/applications/${id}/documents`, fd);
      setNotice(d.duplicate ? "This file was already uploaded." : `Uploaded ${d.file_name}.`);
      setFile(null);
      e.target.reset();
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setBusy(true); setError(null); setNotice(null);
    try {
      await api.post(`/branch/applications/${id}/submit`);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return error ? <ErrorBox error={error} /> : <Loading />;
  const app = data.application;
  const decided = !data.can_upload;

  return (
    <div className="stack">
      {customer && (
        <div className="alert alert-warn">
          <strong>Customer login created — give these to the customer now. The password is shown only once.</strong><br />
          Username <code>{customer.username}</code> · One-time password <code>{customer.temporary_password}</code>
        </div>
      )}
      <Card title={`${app.application_id} · ${app.full_name}`} actions={<StatusBadge status={data.status} />}>
        <div className="facts">
          <div><span>Customer login</span><code>{data.customer_username}</code></div>
          <div><span>PAN</span><code>{app.pan_masked}</code></div>
          <div><span>Application date</span>{fmtDate(app.application_date)}</div>
          <div><span>Decision</span><DecisionBadge decision={data.decision} /></div>
          <div><span>Reason codes</span><Codes codes={data.reason_codes} /></div>
          <div><span>Risk</span>{data.risk_category ?? "—"}</div>
          {data.account_no && <div><span>Account no.</span><strong>{data.account_no}</strong></div>}
        </div>
        {decided && data.status === "IN_REVIEW" && (
          <p className="alert alert-warn">Needs review. Another KYC Officer will pick it up from the Review queue
            (you entered this customer, so you cannot review it).</p>
        )}
        {decided && data.status === "PENDING_CHECKER" && <p className="alert alert-warn">Waiting for a Compliance Officer.</p>}
        {decided && ["AUTO_APPROVED", "APPROVED"].includes(data.status) && <p className="alert alert-ok">Account opened.</p>}
      </Card>

      <Card title="Customer documents">
        <ErrorBox error={error} />
        {notice && <p className="alert alert-ok">{notice}</p>}
        {data.uploaded.length === 0 ? <p className="muted">No documents yet.</p> : (
          <table className="table">
            <thead><tr><th>File</th><th>Declared as</th><th>Uploaded</th></tr></thead>
            <tbody>
              {data.uploaded.map((d) => (
                <tr key={d.doc_id} className={d.superseded ? "superseded" : ""}>
                  <td>{d.file_name}{d.superseded && <span className="muted small"> (replaced)</span>}</td>
                  <td>{DOC_LABELS[d.declared_doc_type]}</td>
                  <td>{fmtDateTime(d.uploaded_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data.can_upload && (
          <>
            <form className="upload" onSubmit={upload}>
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                {DOC_TYPES.map((t) => <option key={t} value={t}>{DOC_LABELS[t]}</option>)}
              </select>
              <input type="file" accept=".txt,text/plain" onChange={(e) => setFile(e.target.files[0] ?? null)} />
              <button className="btn" disabled={!file || busy}>Upload</button>
              <p className="muted small span-all">Scanned documents as .txt (UTF-8, max 1 MB), e.g. <code>data/upload_demo/D3000001.txt</code>.</p>
            </form>
            <button className="btn btn-primary" onClick={submit} disabled={!data.can_submit || busy}>
              {busy ? "Checking…" : "Submit for KYC checks"}
            </button>
            {!data.can_submit && <p className="muted small">Upload at least 3 documents to submit.</p>}
          </>
        )}
      </Card>
      <p><Link to="/branch">Back to branch intake</Link></p>
    </div>
  );
}
