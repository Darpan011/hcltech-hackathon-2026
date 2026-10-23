"""Response shapes. One place decides what each role may see (masking, applicant-safe views)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, AuditLog, Recommendation, RuleResult, ScreeningHitRow, User
from app.services import reference
from app.services.masking import mask_pan
from app.services.rules import ADDRESS, AADHAAR, PAN, format_score, same_date
from app.services.rules_config import RulesConfig
from app.services.screening import normalise
from app.services.workflow import active_documents, current_fields

REASON_MESSAGES = {
    "DOCUMENT_MISSING": "We need your PAN card, Aadhaar card and one address proof.",
    "DOCUMENT_TYPE_MISMATCH": "One of the documents does not match the type you selected.",
    "LOW_EXTRACTION_CONFIDENCE": "Part of a document was hard to read; our team will check it.",
    "AGE_BELOW_18": "You must be 18 or older to open this account.",
    "PAN_INVALID": "The PAN entered is not a valid individual PAN.",
    "PAN_MISMATCH": "The PAN on your PAN card does not match the PAN you entered.",
    "DOB_MISMATCH": "Your date of birth does not match your documents.",
    "AADHAAR_MISMATCH": "The Aadhaar digits do not match your Aadhaar card.",
    "NAME_MISMATCH": "Your name does not match the name on your documents.",
    "NAME_MISMATCH_MINOR": "Your name differs slightly from your documents; our team will check it.",
    "DOCUMENT_EXPIRED": "Your driving licence has expired.",
    "ADDRESS_PROOF_STALE": "Your address proof must be dated within the last 90 days.",
    "ADDRESS_MISMATCH": "The pincode on your address proof does not match your application.",
    "SANCTIONS_MATCH": "Additional verification is required.",
    "SANCTIONS_POSSIBLE_MATCH": "Additional verification is required.",
    "PEP_MATCH": "Additional verification is required.",
    "DUPLICATE_CUSTOMER": "You may already be our customer; our team will check.",
}
STATUS_MESSAGES = {
    "DRAFT": "Your application is saved. Upload at least 3 documents and submit.",
    "SUBMITTED": "We have received your application.",
    "EXTRACTING": "We are checking your documents.",
    "AUTO_APPROVED": "Your account is open.",
    "APPROVED": "Your account is open.",
    "IN_REVIEW": "Our team is reviewing your application.",
    "PENDING_CHECKER": "Your application is waiting for final approval.",
    "RESUBMISSION_REQUESTED": "Please upload new documents.",
    "AUTO_REJECTED": "We could not open your account.",
    "REJECTED": "We could not open your account.",
    "CLOSED_EXPIRED": "This application was closed because new documents were not received in time.",
}


def codes(app: Application) -> list[str]:
    return [c for c in (app.reason_codes or "").split("|") if c]


def user_view(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "roles": u.role_list}


def summary(app: Application) -> dict:
    """Row for lists and queues (PAN masked)."""
    return {
        "application_id": app.application_id, "full_name": app.full_name, "pan_masked": mask_pan(app.pan_number),
        "application_date": app.application_date, "status": app.status, "decision": app.decision,
        "reason_codes": codes(app), "risk_category": app.risk_category,
        "name_match_score": format_score(app.name_match_score) or None,
        "submitted_at": app.submitted_at, "status_changed_at": app.status_changed_at,
        "maker_id": app.maker_id, "maker_action": app.maker_action, "version": app.version,
    }


def _timeline(db: Session, app: Application) -> list[dict]:
    rows = db.scalars(select(AuditLog).where(AuditLog.application_id == app.application_id,
                                             AuditLog.action == "STATUS_CHANGED").order_by(AuditLog.id))
    return [{"ts": r.ts, "status": r.to_status} for r in rows]


def _documents_basic(app: Application) -> list[dict]:
    return [{"doc_id": d.id, "file_name": d.file_name, "declared_doc_type": d.declared_doc_type,
             "uploaded_at": d.uploaded_at, "superseded": d.superseded} for d in app.documents]


def applicant_view(db: Session, app: Application) -> dict:
    """What the applicant may see: no confidence scores, no watchlist details."""
    in_progress = app.status in ("DRAFT", "RESUBMISSION_REQUESTED")
    messages: list[dict] = []
    for c in codes(app):
        msg = REASON_MESSAGES.get(c, "Our team will check your application.")
        if msg not in [m["message"] for m in messages]:
            messages.append({"code": c if not c.startswith(("SANCTIONS", "PEP")) else "ADDITIONAL_CHECKS",
                             "message": msg})
    return {
        "application_id": app.application_id, "full_name": app.full_name, "pan_masked": mask_pan(app.pan_number),
        "application_date": app.application_date, "status": app.status,
        "status_message": STATUS_MESSAGES.get(app.status, ""),
        "reasons": [] if app.status in ("DRAFT", "AUTO_APPROVED", "APPROVED") else messages,
        "customer_id": app.customer_id, "account_no": app.account_no,
        "resubmission_due_at": app.resubmission_due_at,
        "documents": _documents_basic(app), "timeline": _timeline(db, app),
        "can_upload": in_progress, "can_submit": in_progress and len(active_documents(app)) >= 3,
        "version": app.version,
    }


def decision_view(app: Application) -> dict:
    """Decision API response (case §6.3) for staff."""
    docs = []
    for d in active_documents(app):
        dt = current_fields(d).get("doc_type")
        docs.append({"doc_id": d.id, "doc_ref": d.doc_ref, "doc_type": dt.value if dt else None,
                     "confidence": dt.confidence if dt else None})
    return {
        "application_id": app.application_id, "decision": app.decision, "reason_codes": codes(app),
        "name_match_score": float(format_score(app.name_match_score)) if app.name_match_score is not None else None,
        "risk_category": app.risk_category, "rekyc_due_date": app.rekyc_due_date, "status": app.status,
        "version": app.version, "documents": docs, "customer_id": app.customer_id, "account_no": app.account_no,
    }


def staff_application(app: Application) -> dict:
    return {**summary(app), "pan_number": app.pan_number, "dob": app.dob, "gender": app.gender,
            "aadhaar_last4": app.aadhaar_last4, "mobile": app.mobile, "email": app.email, "address": app.address,
            "city": app.city, "state": app.state, "pincode": app.pincode, "occupation_code": app.occupation_code,
            "annual_income": float(app.annual_income), "rekyc_due_date": app.rekyc_due_date,
            "customer_id": app.customer_id, "account_no": app.account_no,
            "resubmission_due_at": app.resubmission_due_at, "owner_id": app.owner_id, "source": app.source}


def review_payload(db: Session, app: Application) -> dict:
    """Everything the KYC Officer / checker needs on one screen (design §10.4 #13)."""
    cfg = RulesConfig.from_dict(reference.config_dict(db))
    latest = db.scalar(select(RuleResult).where(RuleResult.application_id == app.application_id)
                       .order_by(RuleResult.run_no.desc()).limit(1))
    selected: dict = (latest.selected if latest else {}) or {}
    slot_by_ref = {ref: slot for slot, ref in selected.items()}
    users = {u.id: u.full_name for u in db.scalars(select(User))}

    documents, fields_by_ref = [], {}
    for d in app.documents:
        cur = current_fields(d)
        dt = cur.get("doc_type")
        history = {}
        for f in d.fields:
            if not f.is_current:
                history.setdefault(f.field_name, []).append({"value": f.value, "confidence": f.confidence,
                                                             "source": f.source})
        fields = [{
            "field_name": n, "value": f.value, "confidence": f.confidence,
            "usable": bool(str(f.value).strip()) and f.confidence >= cfg.min_field_confidence,
            "source": f.source, "corrected_by": users.get(f.corrected_by) if f.corrected_by else None,
            "correction_reason": f.correction_reason, "previous": history.get(n, []),
        } for n, f in cur.items() if n != "doc_type"]
        if not d.superseded:
            fields_by_ref[d.doc_ref] = (d, cur)
        documents.append({
            "doc_id": d.id, "doc_ref": d.doc_ref, "file_name": d.file_name, "declared_doc_type": d.declared_doc_type,
            "doc_type": dt.value if dt else None, "doc_type_confidence": dt.confidence if dt else None,
            "doc_type_source": dt.source if dt else None,
            "selected_as": None if d.superseded else slot_by_ref.get(d.doc_ref),
            "superseded": d.superseded, "uploaded_at": d.uploaded_at, "fields": fields,
        })

    titles = set(cfg.name_title_tokens)
    rows = [("Name", "name", app.full_name), ("Date of birth", "dob", app.dob.isoformat()),
            ("PAN", "pan_number", app.pan_number), ("Aadhaar last 4", "aadhaar_last4", app.aadhaar_last4),
            ("Pincode", "pincode", app.pincode)]
    comparison = []
    for label, name, declared in rows:
        sources = []
        for slot in (PAN, AADHAAR, ADDRESS):
            entry = fields_by_ref.get(selected.get(slot, ""))
            if not entry or name not in entry[1]:
                continue
            doc, cur = entry
            f = cur[name]
            if name == "name":
                same = normalise(f.value, titles) == normalise(declared, titles)
            elif name == "dob":
                same = same_date(f.value, declared)
            else:
                same = f.value.strip().upper() == declared.strip().upper()
            sources.append({"slot": slot, "doc_id": doc.id, "doc_ref": doc.doc_ref, "value": f.value,
                            "confidence": f.confidence, "usable": f.confidence >= cfg.min_field_confidence,
                            "matches": same})
        comparison.append({"label": label, "field": name, "declared": declared, "sources": sources})

    hits = db.scalars(select(ScreeningHitRow).where(ScreeningHitRow.application_id == app.application_id,
                                                    ScreeningHitRow.run_no == (latest.run_no if latest else 0)))
    recs = db.scalars(select(Recommendation).where(Recommendation.application_id == app.application_id)
                      .order_by(Recommendation.id))
    return {
        "application": staff_application(app),
        "decision": {
            "decision": app.decision, "reason_codes": codes(app),
            "name_match_score": format_score(app.name_match_score) or None,
            "risk_category": app.risk_category, "rekyc_due_date": app.rekyc_due_date,
            "run_no": latest.run_no if latest else None, "trigger": latest.trigger if latest else None,
            "evaluated_at": latest.created_at if latest else None,
        },
        "rule_details": (latest.details if latest else []) or [],
        "selected": selected,
        "documents": documents,
        "comparison": comparison,
        "screening": [{"list_type": h.list_type, "entry_id": h.entry_id, "entry_name": h.entry_name,
                       "matched_on": h.matched_on, "similarity": round(h.similarity, 4), "result": h.result,
                       "dob_comparison": h.dob_comparison, "list_dob": h.list_dob,
                       "applicant_dob": app.dob.isoformat()} for h in hits],
        "recommendations": [{"user_id": r.user_id, "user_name": users.get(r.user_id), "role": r.role,
                             "action": r.action, "comment": r.comment, "created_at": r.created_at} for r in recs],
        "min_field_confidence": cfg.min_field_confidence,
    }
