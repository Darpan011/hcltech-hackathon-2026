import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import api from "../api.js";
import { homeFor, useAuth } from "../auth.jsx";
import { ErrorBox, fieldError } from "../components/ui.jsx";
import { useOnboardingConfig } from "../onboarding.js";

export const SIGN_IN_ROLES = [
  ["APPLICANT", "Applicant"],
  ["KYC_OFFICER", "KYC Officer"],
  ["COMPLIANCE_OFFICER", "Compliance Officer"],
  ["KYC_AND_COMPLIANCE", "KYC + Compliance Officer"],
];

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", password: "", role: "APPLICANT" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const config = useOnboardingConfig();

  if (user) return <Navigate to={homeFor(user)} replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(form.username, form.password, form.role);
      navigate(homeFor(u));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Sign in to OnboardIQ</h1>
        <p className="muted">Deccan Digital Bank · KYC onboarding (synthetic data)</p>
        <ErrorBox error={error} />
        <label>
          Sign in as
          <select id="login-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {SIGN_IN_ROLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          Username
          <input autoFocus value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </label>
        <label>
          Password
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {config?.self_service_onboarding ? (
          <p className="muted small">New applicant? <Link to="/register">Create an account</Link></p>
        ) : (
          <p className="muted small">New customer? Visit your branch with your PAN, Aadhaar and address proof.
            The KYC Officer will open your application and give you your login.</p>
        )}
      </form>
    </div>
  );
}

export function Register() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ username: "", password: "", full_name: "" });
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/auth/register", form);
      await login(form.username, form.password, "APPLICANT");
      navigate("/my");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Create an applicant account</h1>
        <ErrorBox error={error} />
        {[["full_name", "Full name", "text"], ["username", "Username", "text"], ["password", "Password (min 8)", "password"]].map(
          ([name, label, type]) => (
            <label key={name}>
              {label}
              <input type={type} value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })} />
              {fieldError(error, name) && <span className="field-error">{fieldError(error, name)}</span>}
            </label>
          )
        )}
        <button className="btn btn-primary">Create account</button>
        <p className="small"><Link to="/login">Back to sign in</Link></p>
      </form>
    </div>
  );
}
