import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../../api.js";
import { Card, ErrorBox, Loading, StatusBadge, fieldError } from "../../components/ui.jsx";
import { DOC_LABELS, DOC_TYPES, STATUS_LABELS, fmtDate, fmtDateTime } from "../../format.js";
import { useOnboardingConfig } from "../../onboarding.js";

export function MyApplications() {
  const [apps, setApps] = useState(null);
  const [error, setError] = useState(null);
  const config = useOnboardingConfig();
  useEffect(() => {
    api.get("/applications/mine").then((r) => setApps(r.data)).catch(setError);
  }, []);

  return (
    <Card title="My applications"
      actions={config?.self_service_onboarding && <Link className="btn btn-primary" to="/apply">New application</Link>}>
      <ErrorBox error={error} />
      {config && !config.self_service_onboarding && (
        <p className="muted small">Your application was opened at the branch. Track its progress here; visit the branch for a new application.</p>
      )}
      {!apps ? <Loading /> : apps.length === 0 ? <p className="muted">No applications yet.</p> : (
        <table className="table">
          <thead><tr><th>Application</th><th>Name</th><th>Date</th><th>Status</th></tr></thead>
          <tbody>
            {apps.map((a) => (
              <tr key={a.application_id}>
                <td><Link to={`/my/${a.application_id}`}>{a.application_id}</Link></td>
                <td>{a.full_name}</td>
                <td>{fmtDate(a.application_date)}</td>
                <td><StatusBadge status={a.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export const EMPTY = {
  full_name: "", dob: "", gender: "M", pan_number: "", aadhaar_last4: "", mobile: "", email: "",
  address: "", city: "", state: "", pincode: "", occupation_code: "", annual_income: "", consent: false,
};
// Matches data-pack documents D3000001–D3000003 (worked example 1)
export const DEMO = {
  full_name: "Ravi Kumar Sharma", dob: "1990-05-15", gender: "M", pan_number: "ZZKPS1234Q",
  aadhaar_last4: "4821", mobile: "9876500000", email: "ravi@example.com",
  address: "Flat 12, Lotus Residency, MG Road, Mumbai, Maharashtra", city: "Mumbai", state: "Maharashtra",
  pincode: "400001", occupation_code: "SALARIED_PRIVATE", annual_income: "900000", consent: true,
};
export const FIELDS = [
  ["full_name", "Full name (as on PAN)"], ["dob", "Date of birth", "date"], ["pan_number", "PAN"],
  ["aadhaar_last4", "Aadhaar — last 4 digits only"], ["mobile", "Mobile"], ["email", "Email", "email"],
  ["address", "Address"], ["city", "City"], ["state", "State"], ["pincode", "Pincode"],
  ["annual_income", "Annual income (₹)", "number"],
];

/** Application form. mode="self": applicant applies online. mode="branch": KYC Officer enters a walk-in customer. */
export function ApplyForm({ mode = "self" }) {
  const branch = mode === "branch";
  const navigate = useNavigate();
  const [form, setForm] = useState(branch ? { ...EMPTY, username: "" } : EMPTY);
  const [occupations, setOccupations] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/reference/occupations").then((r) => setOccupations(r.data)).catch(setError);
  }, []);

  const set = (name) => (e) => setForm({ ...form, [name]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { ...form, annual_income: form.annual_income === "" ? null : Number(form.annual_income) };
      if (branch) {
        if (!body.username) delete body.username;              // server generates one
        const { data } = await api.post("/branch/applications", body);
        // The one-time password is passed in memory only, shown once on the next screen.
        navigate(`/branch/${data.application_id}`, { state: { customer: data.customer } });
      } else {
        const { data } = await api.post("/applications", body);
        navigate(`/my/${data.application_id}`);
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={branch ? "New walk-in customer (entered at the branch)" : "New savings-account application"}
      actions={<button type="button" className="btn" onClick={() => setForm(branch ? { ...DEMO, username: "" } : DEMO)}>Fill demo data</button>}>
      {branch && <p className="muted small">Enter the details from the customer's form and documents. A login is created for the customer with a one-time password.</p>}
      <ErrorBox error={error} />
      <form className="form-grid" onSubmit={submit} noValidate>
        {FIELDS.map(([name, label, type = "text"]) => (
          <label key={name} className={name === "address" ? "span-2" : ""}>
            {label}
            <input type={type} value={form[name]} onChange={set(name)} />
            {fieldError(error, name) && <span className="field-error">{fieldError(error, name)}</span>}
          </label>
        ))}
        <label>
          Gender
          <select value={form.gender} onChange={set("gender")}>
            <option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
          </select>
        </label>
        <label>
          Occupation
          <select value={form.occupation_code} onChange={set("occupation_code")}>
            <option value="">Select…</option>
            {occupations.map((o) => <option key={o.occupation_code} value={o.occupation_code}>{o.description}</option>)}
          </select>
          {fieldError(error, "occupation_code") && <span className="field-error">{fieldError(error, "occupation_code")}</span>}
        </label>
        {branch && (
          <label>
            Customer login username (optional)
            <input value={form.username} onChange={set("username")} placeholder="Generated if left empty" />
            {fieldError(error, "username") && <span className="field-error">{fieldError(error, "username")}</span>}
          </label>
        )}
        <label className="checkbox span-2">
          <input type="checkbox" checked={form.consent} onChange={set("consent")} />
          {branch ? "Customer has signed consent to KYC checks (identity, address, sanctions and PEP screening)."
            : "I consent to KYC checks (identity, address, sanctions and PEP screening)."}
          {fieldError(error, "consent") && <span className="field-error">{fieldError(error, "consent")}</span>}
        </label>
        <div className="span-2">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : branch ? "Create customer and continue to documents" : "Save and continue to documents"}
          </button>
        </div>
      </form>
    </Card>
  );
}

export function ApplicationDetail() {
  const { id } = useParams();
  const [app, setApp] = useState(null);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [docType, setDocType] = useState("PAN_CARD");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = () => api.get(`/applications/${id}`).then((r) => setApp(r.data)).catch(setError);
  useEffect(() => { load(); }, [id]);

  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("declared_doc_type", docType);
      const { data } = await api.post(`/applications/${id}/documents`, fd);
      setNotice(data.duplicate ? "This file was already uploaded." : `Uploaded ${data.file_name}.`);
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
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const { data } = await api.post(`/applications/${id}/submit`);
      setApp(data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (!app) return error ? <ErrorBox error={error} /> : <Loading />;
  const open = ["AUTO_APPROVED", "APPROVED"].includes(app.status);

  return (
    <div className="stack">
      <Card title={`Application ${app.application_id}`} actions={<StatusBadge status={app.status} />}>
        <p className="lead">{app.status_message}</p>
        {open && (
          <div className="alert alert-ok">
            Account opened · Customer ID <strong>{app.customer_id}</strong> · Account no. <strong>{app.account_no}</strong>
          </div>
        )}
        {app.reasons?.length > 0 && (
          <ul className="reasons">{app.reasons.map((r) => <li key={r.code}>{r.message}</li>)}</ul>
        )}
        {app.resubmission_due_at && app.status === "RESUBMISSION_REQUESTED" && (
          <p className="alert alert-warn">Please upload new documents by <strong>{fmtDate(app.resubmission_due_at)}</strong>.</p>
        )}
        <p className="muted small">Applicant: {app.full_name} · PAN {app.pan_masked} · Applied {fmtDate(app.application_date)}</p>
      </Card>

      <div className="grid-2">
        <Card title="Documents">
          <ErrorBox error={error} />
          {notice && <p className="alert alert-ok">{notice}</p>}
          {app.documents.length === 0 ? <p className="muted">No documents yet.</p> : (
            <table className="table">
              <thead><tr><th>File</th><th>Declared as</th><th>Uploaded</th></tr></thead>
              <tbody>
                {app.documents.map((d) => (
                  <tr key={d.doc_id} className={d.superseded ? "superseded" : ""}>
                    <td>{d.file_name}{d.superseded && <span className="muted small"> (replaced)</span>}</td>
                    <td>{DOC_LABELS[d.declared_doc_type]}</td>
                    <td>{fmtDateTime(d.uploaded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {app.can_upload && (
            <form className="upload" onSubmit={upload}>
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                {DOC_TYPES.map((t) => <option key={t} value={t}>{DOC_LABELS[t]}</option>)}
              </select>
              <input type="file" accept=".txt,text/plain" onChange={(e) => setFile(e.target.files[0] ?? null)} />
              <button className="btn" disabled={!file || busy}>Upload</button>
              <p className="muted small span-all">
                Upload the .txt scans (UTF-8, max 1 MB). Demo files: <code>data/upload_demo/D3000001.txt</code> (PAN),
                <code> D3000002.txt</code> (Aadhaar), <code>D3000003.txt</code> (electricity bill).
              </p>
            </form>
          )}
          {app.can_upload && (
            <button className="btn btn-primary" onClick={submit} disabled={!app.can_submit || busy}>
              {busy ? "Checking…" : "Submit application"}
            </button>
          )}
          {app.can_upload && !app.can_submit && <p className="muted small">Upload at least 3 documents to submit.</p>}
        </Card>

        <Card title="Timeline">
          {app.timeline.length === 0 ? <p className="muted">Not submitted yet.</p> : (
            <ol className="timeline">
              {app.timeline.map((t, i) => (
                <li key={i}><span>{STATUS_LABELS[t.status] ?? t.status}</span><span className="muted small">{fmtDateTime(t.ts)}</span></li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </div>
  );
}
