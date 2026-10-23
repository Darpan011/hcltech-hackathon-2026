"""Compliance dashboard (FR-10). All figures are computed from the stored rows, so they reconcile."""
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import COMPLIANCE_OFFICER, CurrentUser, require_roles
from app.db import get_db
from app.models import Application, AuditLog, RuleResult
from app.services import reference
from app.services.dates import now_ist
from app.services.rules_config import RulesConfig

router = APIRouter(tags=["dashboard"])


def _aware(ts):
    return ts.replace(tzinfo=now_ist().tzinfo) if ts is not None and ts.tzinfo is None else ts


@router.get("/dashboard")
def dashboard(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
              db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles(COMPLIANCE_OFFICER))) -> dict:
    q = select(Application)
    if date_from:
        q = q.where(Application.application_date >= date_from)
    if date_to:
        q = q.where(Application.application_date <= date_to)
    apps = db.scalars(q).all()
    ids = [a.application_id for a in apps]
    by_status = Counter(a.status for a in apps)

    # Rates use the FIRST rules run = what the system decided on its own.
    first = db.scalars(select(RuleResult).where(RuleResult.run_no == 1, RuleResult.application_id.in_(ids))).all() \
        if ids else []
    decided = len(first)
    reasons = Counter(c for r in first for c in (r.reason_codes or "").split("|") if c)

    def rate(n: int) -> float:
        return round(n / decided, 4) if decided else 0.0

    # Average time in review, from STATUS_CHANGED audit rows (enter IN_REVIEW -> next change).
    changes = db.scalars(select(AuditLog).where(AuditLog.action == "STATUS_CHANGED", AuditLog.application_id.in_(ids))
                         .order_by(AuditLog.application_id, AuditLog.id)).all() if ids else []
    durations, entered = [], {}
    for c in changes:
        if c.application_id in entered and c.from_status == "IN_REVIEW":
            durations.append((_aware(c.ts) - entered.pop(c.application_id)).total_seconds() / 60)
        if c.to_status == "IN_REVIEW":
            entered[c.application_id] = _aware(c.ts)

    cfg = RulesConfig.from_dict(reference.config_dict(db))
    pending = [a for a in apps if a.status == "PENDING_CHECKER"]
    overdue = [a for a in pending if a.status_changed_at
               and (now_ist() - _aware(a.status_changed_at)).total_seconds() > cfg.checker_sla_hours * 3600]

    return {
        "filter": {"from": date_from, "to": date_to},
        "total_applications": len(apps),
        "by_status": dict(sorted(by_status.items())),
        "by_risk": dict(Counter(a.risk_category or "NONE" for a in apps)),
        "decided": decided,
        "straight_through_rate": rate(by_status.get("AUTO_APPROVED", 0)),
        "review_rate": rate(sum(1 for r in first if r.decision == "REVIEW")),
        "reject_rate": rate(sum(1 for r in first if r.decision == "REJECT")),
        "top_reason_codes": [{"code": c, "count": n} for c, n in reasons.most_common(5)],
        "avg_time_in_review_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "reviews_completed": len(durations),
        "pending_checker": len(pending),
        "pending_checker_overdue": len(overdue),
        "accounts_opened": by_status.get("AUTO_APPROVED", 0) + by_status.get("APPROVED", 0),
    }
