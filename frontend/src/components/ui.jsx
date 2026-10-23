import { STATUS_LABELS, statusTone } from "../format.js";

export function StatusBadge({ status }) {
  return <span className={`badge badge-${statusTone(status)}`}>{STATUS_LABELS[status] ?? status}</span>;
}

export function RiskBadge({ risk }) {
  if (!risk) return <span className="muted">—</span>;
  const tone = risk === "HIGH" ? "danger" : risk === "MEDIUM" ? "warn" : "ok";
  return <span className={`badge badge-${tone}`}>{risk}</span>;
}

export function DecisionBadge({ decision }) {
  if (!decision) return <span className="muted">—</span>;
  const tone = decision === "APPROVE" ? "ok" : decision === "REJECT" ? "danger" : "warn";
  return <span className={`badge badge-${tone}`}>{decision}</span>;
}

export function Codes({ codes }) {
  if (!codes?.length) return <span className="muted">none</span>;
  return (
    <span className="chips">
      {codes.map((c) => (
        <span key={c} className="chip">{c}</span>
      ))}
    </span>
  );
}

/** Shows an API error ({message, fields}) in one consistent style. */
export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div className="alert alert-danger" role="alert">
      <strong>{error.message}</strong>
      {error.fields?.length > 0 && (
        <ul>
          {error.fields.map((f, i) => (
            <li key={i}>
              {f.field ? <code>{f.field}</code> : null} {f.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function fieldError(error, name) {
  return error?.fields?.find((f) => f.field === name)?.message;
}

export function Loading({ what = "Loading" }) {
  return <p className="muted">{what}…</p>;
}

export function Card({ title, actions, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
