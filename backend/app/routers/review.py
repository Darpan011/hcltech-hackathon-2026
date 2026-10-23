"""KYC Officer workbench (FR-6) and Compliance checker (FR-7)."""
from fastapi import APIRouter, Depends
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.auth import COMPLIANCE_OFFICER, KYC_OFFICER, CurrentUser, get_application_for, require_roles
from app.db import get_db
from app.models import Application, Recommendation, User
from app.schemas import CheckIn, FieldCorrectionIn, RecommendIn
from app.services import reference, workflow
from app.services.dates import now_ist
from app.services.rules_config import RulesConfig
from app.views import review_payload, summary

router = APIRouter(tags=["review"])
officer = require_roles(KYC_OFFICER)
checker = require_roles(COMPLIANCE_OFFICER)
staff = require_roles(KYC_OFFICER, COMPLIANCE_OFFICER)


@router.get("/review/queue")
def review_queue(db: Session = Depends(get_db), user: CurrentUser = Depends(officer)) -> list:
    """IN_REVIEW cases: HIGH risk first, then oldest submission first."""
    risk_order = case({"HIGH": 0, "MEDIUM": 1, "LOW": 2}, value=Application.risk_category, else_=3)
    apps = db.scalars(select(Application).where(Application.status == "IN_REVIEW")
                      .order_by(risk_order, Application.submitted_at, Application.application_id))
    return [summary(a) for a in apps]


@router.get("/applications/{application_id}/review")
def review(application_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(staff)) -> dict:
    return review_payload(db, get_application_for(db, application_id, user))


@router.patch("/applications/{application_id}/fields")
def correct_field(application_id: str, body: FieldCorrectionIn, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(officer)) -> dict:
    app = get_application_for(db, application_id, user)
    workflow.correct_field(db, app, (user.id, KYC_OFFICER), body.doc_id, body.field_name, body.value,
                           body.reason, body.version)
    db.commit()
    return review_payload(db, app)


@router.post("/applications/{application_id}/recommend")
def recommend(application_id: str, body: RecommendIn, db: Session = Depends(get_db),
              user: CurrentUser = Depends(officer)) -> dict:
    app = get_application_for(db, application_id, user)
    workflow.recommend(db, app, (user.id, KYC_OFFICER), body.action, body.comment, body.version)
    db.commit()
    return {"application_id": app.application_id, "status": app.status, "maker_id": app.maker_id,
            "resubmission_due_at": app.resubmission_due_at, "version": app.version}


@router.get("/checker/queue")
def checker_queue(db: Session = Depends(get_db), user: CurrentUser = Depends(checker)) -> list:
    """PENDING_CHECKER cases, oldest first, with the maker's recommendation and SLA flag."""
    cfg = RulesConfig.from_dict(reference.config_dict(db))
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    apps = db.scalars(select(Application).where(Application.status == "PENDING_CHECKER")
                      .order_by(Application.status_changed_at, Application.application_id)).all()
    out = []
    for a in apps:
        last = db.scalar(select(Recommendation).where(Recommendation.application_id == a.application_id)
                         .order_by(Recommendation.id.desc()).limit(1))
        since = a.status_changed_at
        if since is not None and since.tzinfo is None:
            since = since.replace(tzinfo=now_ist().tzinfo)
        hours = (now_ist() - since).total_seconds() / 3600 if since else 0
        out.append({**summary(a), "maker_name": names.get(a.maker_id),
                    "maker_comment": last.comment if last and a.maker_id else None,
                    "route": "HIGH_RISK_APPROVAL" if a.maker_id is None else "OFFICER_RECOMMENDATION",
                    "pending_hours": round(hours, 1), "sla_overdue": hours > cfg.checker_sla_hours})
    return out


@router.post("/applications/{application_id}/check")
def check(application_id: str, body: CheckIn, db: Session = Depends(get_db),
          user: CurrentUser = Depends(checker)) -> dict:
    app = get_application_for(db, application_id, user)
    workflow.check(db, app, (user.id, COMPLIANCE_OFFICER), body.action, body.comment, body.version)
    db.commit()
    return {"application_id": app.application_id, "status": app.status, "customer_id": app.customer_id,
            "account_no": app.account_no, "version": app.version}
