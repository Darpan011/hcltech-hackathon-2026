"""Append-only audit trail. Rows are added to the caller's session, so they commit
(or roll back) together with the change they describe."""
from sqlalchemy.orm import Session

from app.models import AuditLog

SYSTEM = ("SYSTEM", "SYSTEM")


def log(db: Session, *, action: str, entity: str, entity_id: str, actor: tuple[str, str],
        application_id: str | None = None, from_status: str | None = None, to_status: str | None = None,
        before: dict | None = None, after: dict | None = None, comment: str | None = None) -> None:
    """Record one audit event. `actor` is (user_id, role used for this action)."""
    db.add(AuditLog(
        entity=entity, entity_id=entity_id, application_id=application_id,
        actor_id=actor[0], actor_role=actor[1], action=action,
        from_status=from_status, to_status=to_status, before=before, after=after, comment=comment,
    ))
