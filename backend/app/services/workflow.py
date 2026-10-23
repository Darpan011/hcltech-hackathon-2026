"""Application workflow (design §9): status state machine, submit -> extract -> decide -> route,
officer field correction, maker-checker, resubmission and expiry.

Every status change goes through transition(): checked against ALLOWED, audited in the same
transaction, and flushed with the optimistic-lock version check (concurrent change -> 409).
"""
import hashlib
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.events import queue_event
from app.models import (AppSequence, Application, AuditLog, Document, ExtractedField, Recommendation, RuleResult,
                        ScreeningHitRow)
from app.services import audit, reference
from app.services.core_banking import open_account
from app.services.dates import now_ist, parse_date, today_ist
from app.services.extraction import get_provider
from app.services.masking import mask_account
from app.services.rules import DOC_TYPES, AppInput, Decision, DocInput, Field, decide, format_score, route
from app.settings import settings

Actor = tuple[str, str]           # (user_id, role used for the action)
SYSTEM = audit.SYSTEM

ALLOWED: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"EXTRACTING"},
    "EXTRACTING": {"AUTO_APPROVED", "PENDING_CHECKER", "IN_REVIEW", "AUTO_REJECTED"},
    "IN_REVIEW": {"PENDING_CHECKER", "RESUBMISSION_REQUESTED"},
    "RESUBMISSION_REQUESTED": {"SUBMITTED", "CLOSED_EXPIRED"},
    "PENDING_CHECKER": {"APPROVED", "REJECTED", "IN_REVIEW"},
}
FINAL_STATUSES = {"AUTO_APPROVED", "APPROVED", "REJECTED", "AUTO_REJECTED", "CLOSED_EXPIRED"}
CORRECTABLE_FIELDS = {"doc_type", "name", "dob", "gender", "pan_number", "aadhaar_last4", "address",
                      "pincode", "document_date", "valid_until"}
MAX_UPLOAD_BYTES = 1024 * 1024


def business_today():
    """Application date for new applications (BUSINESS_DATE if set, else today in IST)."""
    return parse_date(settings.business_date) or today_ist()


def new_application_id(db: Session) -> str:
    seq = AppSequence()
    db.add(seq)
    db.flush()
    return f"A{9000000 + seq.id}"


# ---------------- state machine ----------------

def transition(db: Session, app: Application, to: str, actor: Actor, comment: str | None = None) -> None:
    frm = app.status
    if to not in ALLOWED.get(frm, set()):
        raise ApiError(409, "INVALID_STATUS_TRANSITION", f"Cannot move an application from {frm} to {to}")
    app.status = to
    app.status_changed_at = now_ist()
    audit.log(db, action="STATUS_CHANGED", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=actor, from_status=frm, to_status=to, comment=comment)
    db.flush()   # versioned UPDATE: raises StaleDataError (-> 409) if someone else changed the row


def entered_by(db: Session, app: Application) -> str | None:
    """User who entered a branch application (from the audit trail)."""
    if app.source != "BRANCH":
        return None
    return db.scalar(select(AuditLog.actor_id).where(AuditLog.application_id == app.application_id,
                                                     AuditLog.action == "APPLICATION_CREATED").limit(1))


def require_not_data_entry_officer(db: Session, app: Application, actor: Actor) -> None:
    """Segregation of duties: whoever typed the customer's data at the branch can't also review it."""
    if entered_by(db, app) == actor[0]:
        raise ApiError(403, "DATA_ENTRY_CANNOT_REVIEW",
                       "You entered this customer's data at the branch; another KYC Officer must review it")


def check_version(app: Application, version: int | None) -> None:
    if version is not None and version != app.version:
        raise ApiError(409, "CONFLICT", "This case was changed by someone else. Reload it and try again.")


def require_status(app: Application, *statuses: str) -> None:
    if app.status not in statuses:
        raise ApiError(409, "INVALID_STATUS_TRANSITION",
                       f"This action needs status {' or '.join(statuses)}; the application is {app.status}")


# ---------------- documents ----------------

def active_documents(app: Application) -> list[Document]:
    return [d for d in app.documents if not d.superseded]


def current_fields(doc: Document) -> dict[str, ExtractedField]:
    return {f.field_name: f for f in doc.fields if f.is_current}


def read_text(doc: Document) -> str:
    p = Path(doc.storage_path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def add_document(db: Session, app: Application, actor: Actor, filename: str, content: bytes,
                 declared_doc_type: str) -> tuple[Document, bool]:
    """Validate and store one .txt upload. Returns (document, was_duplicate)."""
    require_status(app, "DRAFT", "RESUBMISSION_REQUESTED")
    if declared_doc_type not in DOC_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "Choose a valid document type",
                       [{"field": "declared_doc_type", "message": f"Must be one of {', '.join(DOC_TYPES)}"}])
    if not filename.lower().endswith(".txt") or not content or len(content) > MAX_UPLOAD_BYTES:
        raise ApiError(400, "INVALID_FILE", "Only UTF-8 .txt files up to 1 MB are allowed")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        raise ApiError(400, "INVALID_FILE", "Only UTF-8 .txt files up to 1 MB are allowed")

    sha = hashlib.sha256(content).hexdigest()
    existing = next((d for d in app.documents if d.sha256 == sha), None)
    if existing:
        return existing, True

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored = upload_dir / f"{sha}.txt"          # content-addressed; never executed
    if not stored.exists():
        stored.write_bytes(content)

    if app.status == "RESUBMISSION_REQUESTED":   # assumption A6: new upload replaces same declared type
        for old in active_documents(app):
            if old.declared_doc_type == declared_doc_type:
                old.superseded = True
                audit.log(db, action="DOCUMENT_SUPERSEDED", entity="DOCUMENT", entity_id=old.id,
                          application_id=app.application_id, actor=actor)

    doc_ref = re.sub(r"[^A-Za-z0-9_-]", "", Path(filename).stem)[:40] or "DOC"
    doc = Document(doc_ref=doc_ref, file_name=Path(filename).name[:255], declared_doc_type=declared_doc_type,
                   sha256=sha, size_bytes=len(content), storage_path=str(stored), superseded=False)
    app.documents.append(doc)
    db.flush()
    audit.log(db, action="DOCUMENT_UPLOADED", entity="DOCUMENT", entity_id=doc.id, application_id=app.application_id,
              actor=actor, after={"file_name": doc.file_name, "declared_doc_type": declared_doc_type, "sha256": sha})
    return doc, False


def extract_documents(db: Session, app: Application) -> None:
    """Run the configured extraction provider on every active document not yet extracted."""
    provider = get_provider(db)
    for doc in active_documents(app):
        if current_fields(doc):
            continue          # keep earlier results (and any officer corrections)
        res = provider.extract(doc.doc_ref, read_text(doc))
        source = res.provider.upper()
        # is_current is set explicitly: column defaults only apply at INSERT, and the rules
        # read these objects in memory before the flush.
        doc.fields.append(ExtractedField(field_name="doc_type", value=res.doc_type, confidence=res.doc_type_confidence,
                                         source=source, provider=res.provider, is_current=True))
        for name, value, conf in res.fields:
            doc.fields.append(ExtractedField(field_name=name, value=value, confidence=conf,
                                             source=source, provider=res.provider, is_current=True))
        audit.log(db, action="EXTRACTION_COMPLETED", entity="DOCUMENT", entity_id=doc.id,
                  application_id=app.application_id, actor=SYSTEM,
                  after={"provider": res.provider, "doc_type": res.doc_type,
                         "confidence": res.doc_type_confidence, "fields": len(res.fields)})
    db.flush()


# ---------------- rules ----------------

def build_inputs(app: Application) -> tuple[AppInput, list[DocInput]]:
    app_in = AppInput(app.application_id, app.application_date, app.full_name, app.dob.isoformat(),
                      app.pan_number, app.aadhaar_last4, app.pincode, app.occupation_code, float(app.annual_income))
    docs = []
    for d in active_documents(app):
        cur = current_fields(d)
        dt = cur.get("doc_type")
        fields = {n: Field(f.value, f.confidence) for n, f in cur.items() if n != "doc_type"}
        docs.append(DocInput(d.doc_ref, d.declared_doc_type, dt.value if dt else "OTHER",
                             dt.confidence if dt else 0.0, fields))
    return app_in, docs


def evaluate(db: Session, app: Application, trigger: str, actor: Actor) -> Decision:
    """Run the rules engine, store the run + hits, copy the result onto the application."""
    cfg, ref = reference.load(db)
    d = decide(*build_inputs(app), cfg, ref)
    db.flush()
    run_no = (db.scalar(select(func.max(RuleResult.run_no))
                        .where(RuleResult.application_id == app.application_id)) or 0) + 1
    db.add(RuleResult(application_id=app.application_id, run_no=run_no, trigger=trigger, decision=d.decision,
                      reason_codes="|".join(d.reason_codes), name_match_score=d.name_match_score,
                      risk_category=d.risk_category, rekyc_due_date=d.rekyc_due_date,
                      details=d.rule_details, selected=d.selected))
    for h in d.hits:
        db.add(ScreeningHitRow(application_id=app.application_id, run_no=run_no, list_type=h.list_type,
                               entry_id=h.entry_id, entry_name=h.entry_name, matched_on=h.matched_on,
                               similarity=h.similarity, result=h.result, dob_comparison=h.dob_comparison,
                               list_dob=h.list_dob))
        audit.log(db, action="WATCHLIST_HIT", entity="APPLICATION", entity_id=app.application_id,
                  application_id=app.application_id, actor=SYSTEM, after=h.as_dict())
    app.decision = d.decision
    app.reason_codes = "|".join(d.reason_codes)
    app.name_match_score = d.name_match_score
    app.risk_category = d.risk_category
    app.rekyc_due_date = d.rekyc_due_date
    audit.log(db, action="RULES_EVALUATED", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=actor,
              after={"run_no": run_no, "trigger": trigger, "decision": d.decision, "reason_codes": d.reason_codes,
                     "name_match_score": format_score(d.name_match_score), "risk_category": d.risk_category,
                     "rekyc_due_date": d.rekyc_due_date.isoformat() if d.rekyc_due_date else None})
    db.flush()
    return d


def _open_account(db: Session, app: Application, actor: Actor) -> None:
    app.customer_id, app.account_no = open_account(app.application_id, settings.core_banking_key)
    audit.log(db, action="ACCOUNT_OPENED", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=actor,
              after={"customer_id": app.customer_id, "account_no": mask_account(app.account_no)})
    queue_event(db, "ACCOUNT_OPENED", app.application_id, {"account_no_masked": mask_account(app.account_no)})


# ---------------- use cases ----------------

def submit(db: Session, app: Application, actor: Actor, enforce_min_documents: bool = True) -> Decision:
    """Applicant submits: extract every document, run the rules, route (design §9.3).

    The ">= 3 documents" check is the upload screen's input rule (case §4). Seeding the
    data pack's historical applications skips it, so R1 DOCUMENT_MISSING decides them instead.
    """
    require_status(app, "DRAFT", "RESUBMISSION_REQUESTED")
    if enforce_min_documents and len(active_documents(app)) < 3:
        raise ApiError(422, "VALIDATION_ERROR", "Upload at least 3 documents",
                       [{"field": "documents", "message": "Upload at least 3 documents"}])
    app.submitted_at = now_ist()
    app.maker_id = app.maker_action = app.resubmission_due_at = None
    transition(db, app, "SUBMITTED", actor)
    transition(db, app, "EXTRACTING", SYSTEM)
    extract_documents(db, app)
    d = evaluate(db, app, "SUBMIT", SYSTEM)
    to = route(d)
    transition(db, app, to, SYSTEM)
    if to == "AUTO_APPROVED":
        _open_account(db, app, SYSTEM)
    queue_event(db, "APPLICATION_SUBMITTED", app.application_id)
    queue_event(db, "DECISION_MADE", app.application_id, {"status": to, "decision": d.decision})
    return d


def correct_field(db: Session, app: Application, actor: Actor, doc_id: str, field_name: str, value: str,
                  reason: str, version: int | None) -> Decision:
    """KYC Officer fixes a misread field; the rules re-run; the case still goes to the checker."""
    check_version(app, version)          # stale screen first: clearer than a status error
    require_status(app, "IN_REVIEW")
    require_not_data_entry_officer(db, app, actor)
    doc = next((d for d in active_documents(app) if d.id == doc_id), None)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document not found on this application")
    if field_name not in CORRECTABLE_FIELDS:
        raise ApiError(422, "VALIDATION_ERROR", "This field cannot be corrected",
                       [{"field": "field_name", "message": f"Must be one of {', '.join(sorted(CORRECTABLE_FIELDS))}"}])
    value = _validate_field_value(field_name, value)

    old = current_fields(doc).get(field_name)
    if old:
        old.is_current = False
    doc.fields.append(ExtractedField(field_name=field_name, value=value, confidence=1.0, source="OFFICER",
                                     provider="officer", corrected_by=actor[0], correction_reason=reason,
                                     is_current=True))
    audit.log(db, action="FIELD_CORRECTED", entity="DOCUMENT", entity_id=doc.id, application_id=app.application_id,
              actor=actor, comment=reason,
              before={"field": field_name, "value": old.value if old else None,
                      "confidence": old.confidence if old else None, "source": old.source if old else None},
              after={"field": field_name, "value": value, "confidence": 1.0, "source": "OFFICER"})
    return evaluate(db, app, "CORRECTION", actor)


def _validate_field_value(field_name: str, value: str) -> str:
    v = (value or "").strip()

    def bad(msg: str):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid corrected value", [{"field": "value", "message": msg}])

    if field_name == "doc_type":
        if v not in DOC_TYPES + ("OTHER",):
            bad("Unknown document type")
    elif field_name in ("dob", "document_date", "valid_until"):
        d = parse_date(v)
        if d is None:
            bad("Use a valid date in YYYY-MM-DD format")
        v = d.isoformat()
    elif field_name == "pan_number":
        v = v.upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", v):
            bad("PAN must look like ABCDE1234F")
    elif field_name == "aadhaar_last4":
        if not re.fullmatch(r"[0-9]{4}", v):
            bad("Enter only the last 4 digits of Aadhaar")
    elif field_name == "pincode":
        if not re.fullmatch(r"[1-9][0-9]{5}", v):
            bad("Pincode must be 6 digits and not start with 0")
    elif field_name == "gender":
        v = v.upper()
        if v not in ("M", "F", "O"):
            bad("Gender must be M, F or O")
    elif not v or len(v) > 300:
        bad("Value is required (max 300 characters)")
    return v


def recommend(db: Session, app: Application, actor: Actor, action: str, comment: str, version: int | None) -> None:
    """KYC Officer (maker) recommendation."""
    check_version(app, version)
    require_status(app, "IN_REVIEW")
    require_not_data_entry_officer(db, app, actor)
    db.add(Recommendation(application_id=app.application_id, user_id=actor[0], role=actor[1],
                          action=action, comment=comment))
    audit.log(db, action="RECOMMENDATION_MADE", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=actor, after={"action": action}, comment=comment)
    if action == "REQUEST_RESUBMISSION":
        cfg, _ = reference.load(db)
        app.resubmission_due_at = now_ist() + timedelta(days=cfg.resubmission_sla_days)
        transition(db, app, "RESUBMISSION_REQUESTED", actor, comment)
        queue_event(db, "RESUBMISSION_REQUESTED", app.application_id,
                    {"due_date": app.resubmission_due_at.date().isoformat()})
    else:
        app.maker_id, app.maker_action = actor[0], action
        transition(db, app, "PENDING_CHECKER", actor, comment)


def check(db: Session, app: Application, actor: Actor, action: str, comment: str, version: int | None) -> None:
    """Compliance Officer (checker) final decision; must not be the maker."""
    check_version(app, version)
    require_status(app, "PENDING_CHECKER")
    if app.maker_id == actor[0]:
        raise ApiError(403, "MAKER_CANNOT_CHECK", "You recommended this case; a different checker must decide")
    db.add(Recommendation(application_id=app.application_id, user_id=actor[0], role=actor[1],
                          action=action, comment=comment))
    audit.log(db, action="CHECKER_DECISION", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=actor,
              after={"action": action, "maker_id": app.maker_id, "maker_action": app.maker_action}, comment=comment)
    if action == "APPROVE":
        transition(db, app, "APPROVED", actor, comment)
        _open_account(db, app, actor)
        queue_event(db, "CHECKER_DECISION", app.application_id, {"status": "APPROVED"})
    elif action == "REJECT":
        transition(db, app, "REJECTED", actor, comment)
        queue_event(db, "CHECKER_DECISION", app.application_id, {"status": "REJECTED"})
    else:  # SEND_BACK: back to the officer queue; a new recommendation will be needed
        app.maker_id = app.maker_action = None
        transition(db, app, "IN_REVIEW", actor, comment)


def expire_if_due(db: Session, app: Application) -> bool:
    """Close an application whose resubmission window has passed. Returns True if it changed."""
    if app.status != "RESUBMISSION_REQUESTED" or not app.resubmission_due_at:
        return False
    due = app.resubmission_due_at
    if due.tzinfo is None:                       # SQLite returns naive datetimes
        due = due.replace(tzinfo=now_ist().tzinfo)
    if now_ist() <= due:
        return False
    transition(db, app, "CLOSED_EXPIRED", SYSTEM, "No resubmission within the allowed window")
    queue_event(db, "APPLICATION_EXPIRED", app.application_id)
    return True
