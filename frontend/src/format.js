export const STATUS_LABELS = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  EXTRACTING: "Checking documents",
  AUTO_APPROVED: "Auto-approved",
  APPROVED: "Approved",
  IN_REVIEW: "In review",
  PENDING_CHECKER: "Pending checker",
  RESUBMISSION_REQUESTED: "Resubmission requested",
  AUTO_REJECTED: "Auto-rejected",
  REJECTED: "Rejected",
  CLOSED_EXPIRED: "Closed (expired)",
};

export const DOC_TYPES = ["PAN_CARD", "AADHAAR_CARD", "ELECTRICITY_BILL", "BANK_STATEMENT", "DRIVING_LICENCE"];

export const DOC_LABELS = {
  PAN_CARD: "PAN card",
  AADHAAR_CARD: "Aadhaar card",
  ELECTRICITY_BILL: "Electricity bill",
  BANK_STATEMENT: "Bank statement",
  DRIVING_LICENCE: "Driving licence",
  ADDRESS_PROOF: "Address proof",
  OTHER: "Other / unknown",
};

export function statusTone(status) {
  if (["AUTO_APPROVED", "APPROVED"].includes(status)) return "ok";
  if (["AUTO_REJECTED", "REJECTED", "CLOSED_EXPIRED"].includes(status)) return "danger";
  if (["IN_REVIEW", "PENDING_CHECKER", "RESUBMISSION_REQUESTED"].includes(status)) return "warn";
  return "neutral";
}

export function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export const pct = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
export const conf = (x) => (x == null ? "—" : Number(x).toFixed(2));
