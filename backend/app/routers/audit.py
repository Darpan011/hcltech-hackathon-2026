"""Audit trail view and CSV export (FR-9). Read-only: no update or delete endpoint exists."""
import csv
import io
import json
import re

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import COMPLIANCE_OFFICER, CurrentUser, get_application_for, require_roles
from app.db import get_db
from app.models import AuditLog

router = APIRouter(tags=["audit"])
checker = require_roles(COMPLIANCE_OFFICER)
_PAN = re.compile(r"\b([A-Z]{3})[A-Z]{2}[0-9]{4}([A-Z])\b")
COLUMNS = ["id", "ts", "entity", "entity_id", "actor_id", "actor_role", "action",
           "from_status", "to_status", "before", "after", "comment"]


def _mask(value):
    """Mask any PAN inside audit payloads (lists and exports must not show full PANs)."""
    if value is None:
        return None
    text = json.dumps(value) if not isinstance(value, str) else value
    masked = _PAN.sub(lambda m: f"{m.group(0)[:3]}XXXXX{m.group(0)[-2:]}", text)
    return json.loads(masked) if not isinstance(value, str) else masked


def _rows(db: Session, application_id: str) -> list[dict]:
    rows = db.scalars(select(AuditLog).where(or_(AuditLog.application_id == application_id,
                                                 AuditLog.entity_id == application_id)).order_by(AuditLog.id))
    return [{"id": r.id, "ts": r.ts, "entity": r.entity, "entity_id": r.entity_id, "actor_id": r.actor_id,
             "actor_role": r.actor_role, "action": r.action, "from_status": r.from_status,
             "to_status": r.to_status, "before": _mask(r.before), "after": _mask(r.after),
             "comment": _mask(r.comment)} for r in rows]


@router.get("/applications/{application_id}/audit")
def audit_trail(application_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(checker)) -> list:
    get_application_for(db, application_id, user)
    return _rows(db, application_id)


@router.get("/applications/{application_id}/audit/export")
def audit_export(application_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(checker)):
    get_application_for(db, application_id, user)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    for row in _rows(db, application_id):
        writer.writerow({**row, "ts": row["ts"].isoformat() if row["ts"] else "",
                         "before": json.dumps(row["before"]) if row["before"] is not None else "",
                         "after": json.dumps(row["after"]) if row["after"] is not None else ""})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="audit_{application_id}.csv"'})
