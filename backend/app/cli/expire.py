"""Close applications whose 7-day resubmission window has passed.  python -m app.cli.expire"""
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Application
from app.services.workflow import expire_if_due


def main() -> None:
    with SessionLocal() as db:
        apps = db.scalars(select(Application).where(Application.status == "RESUBMISSION_REQUESTED")).all()
        closed = [a.application_id for a in apps if expire_if_due(db, a)]
        db.commit()
    print(f"Closed {len(closed)} expired application(s): {', '.join(closed) or '-'}")


if __name__ == "__main__":
    main()
