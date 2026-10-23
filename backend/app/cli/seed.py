"""Seed reference data, demo users and (optionally) the data-pack applications. Idempotent.

  python -m app.cli.seed                      # config, lists, mock extraction, users
  python -m app.cli.seed --with-sample-apps   # + the 60 sample applications, decided by the real workflow
  python -m app.cli.seed --with-eval-apps     # + the 100 evaluation applications
  python -m app.cli.seed --reset ...          # drop everything first
"""
import argparse
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import APPLICANT, COMPLIANCE_OFFICER, KYC_OFFICER, hash_password
from app.db import Base, SessionLocal, create_tables, engine
from app.models import (Application, ConfigEntry, ExistingCustomer, MockExtraction, Occupation, PepEntry,
                        SanctionsEntry, User)
from app.services import datapack, workflow
from app.services.dates import parse_date
from app.settings import settings

DEMO_USERS = [  # (id, username, full name, roles)
    ("U0", "applicant_demo", "Demo Applicant", APPLICANT),
    ("U1", "officer1", "Officer One (KYC)", KYC_OFFICER),
    ("U3", "officer2", "Officer Two (KYC)", KYC_OFFICER),
    ("U2", "checker1", "Checker One (Compliance)", COMPLIANCE_OFFICER),
    ("U4", "checker2", "Checker Two (Compliance)", COMPLIANCE_OFFICER),
    ("U5", "officer_checker", "Dual-role User (KYC + Compliance)", f"{KYC_OFFICER},{COMPLIANCE_OFFICER}"),
]


def _empty(db: Session, model) -> bool:
    return not db.scalar(select(func.count()).select_from(model))


def seed_reference(db: Session, data_dir: Path) -> None:
    if _empty(db, ConfigEntry):
        for key, value in datapack.read_config(datapack.path(data_dir, "rules_config")).items():
            db.add(ConfigEntry(key=key, value=value))
    if _empty(db, Occupation):
        db.add_all(Occupation(**r) for r in datapack.read_csv(datapack.path(data_dir, "occupations")))
    if _empty(db, SanctionsEntry):
        db.add_all(SanctionsEntry(**r) for r in datapack.read_csv(datapack.path(data_dir, "sanctions")))
    if _empty(db, PepEntry):
        db.add_all(PepEntry(**r) for r in datapack.read_csv(datapack.path(data_dir, "pep")))
    if _empty(db, ExistingCustomer):
        db.add_all(ExistingCustomer(**r) for r in datapack.read_csv(datapack.path(data_dir, "existing_customers")))
    if _empty(db, MockExtraction):
        for key in ("extraction_sample", "extraction_eval"):
            f = datapack.path(data_dir, key)
            if f.exists():
                db.add_all(MockExtraction(doc_id=r["doc_id"], field_name=r["field_name"], value=r["value"],
                                          confidence=float(r["confidence"])) for r in datapack.read_csv(f))
    db.commit()


def seed_users(db: Session) -> None:
    for uid, username, name, roles in DEMO_USERS:
        if db.get(User, uid) is None:
            db.add(User(id=uid, username=username, full_name=name, roles=roles,
                        password_hash=hash_password(settings.seed_password)))
    db.commit()


def write_upload_demo(data_dir: Path, out_dir: Path) -> int:
    """Write every data-pack document as <doc_id>.txt so it can be uploaded through the UI."""
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for key in ("text_sample", "text_eval"):
        f = datapack.path(data_dir, key)
        if f.exists():
            for d in datapack.read_jsonl(f):
                (out_dir / d["file_name"]).write_text(d["text"], encoding="utf-8")
                count += 1
    return count


def seed_applications(db: Session, data_dir: Path, set_name: str) -> int:
    """Create the data-pack applications and decide them through the real submit workflow."""
    apps = datapack.read_csv(datapack.path(data_dir, f"applications_{set_name}"))
    if db.get(Application, apps[0]["application_id"]) is not None:
        return 0
    docs: dict[str, list[dict]] = {}
    for row in datapack.read_csv(datapack.path(data_dir, f"documents_{set_name}")):
        docs.setdefault(row["application_id"], []).append(row)
    texts = {d["doc_id"]: d["text"] for d in datapack.read_jsonl(datapack.path(data_dir, f"text_{set_name}"))}
    actor = ("U0", APPLICANT)
    db.info["suppress_events"] = True     # seeding history is not live activity: no notifications
    for row in apps:
        app = Application(
            application_id=row["application_id"], owner_id="U0", source="SEED",
            application_date=parse_date(row["application_date"]), full_name=row["full_name"],
            dob=parse_date(row["dob"]), gender=row["gender"], pan_number=row["pan_number"],
            aadhaar_last4=row["aadhaar_last4"], mobile=row["mobile"], email=row["email"], address=row["address"],
            city=row["city"], state=row["state"], pincode=row["pincode"], occupation_code=row["occupation_code"],
            annual_income=float(row["annual_income"] or 0), consent=True, status="DRAFT",
        )
        db.add(app)
        db.flush()
        for d in docs.get(row["application_id"], []):
            workflow.add_document(db, app, actor, d["file_name"], texts.get(d["doc_id"], "").encode("utf-8"),
                                  d["declared_doc_type"])
        workflow.submit(db, app, actor, enforce_min_documents=False)
        db.commit()
    return len(apps)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reset", action="store_true", help="drop all tables first")
    p.add_argument("--with-sample-apps", action="store_true")
    p.add_argument("--with-eval-apps", action="store_true")
    p.add_argument("--data-dir", default=settings.data_dir)
    a = p.parse_args()
    data_dir = Path(a.data_dir)

    if a.reset:
        from app import models  # noqa: F401
        Base.metadata.drop_all(engine)
        print("Dropped all tables")
    create_tables()
    with SessionLocal() as db:
        seed_reference(db, data_dir)
        seed_users(db)
        print(f"Reference data and {len(DEMO_USERS)} demo users ready")
        try:
            n = write_upload_demo(data_dir, Path(settings.upload_demo_dir))
            print(f"Wrote {n} demo documents to {settings.upload_demo_dir}")
        except OSError as exc:
            print(f"Skipped demo documents: {exc}")
        if a.with_sample_apps:
            print(f"Sample applications created: {seed_applications(db, data_dir, 'sample')}")
        if a.with_eval_apps:
            print(f"Evaluation applications created: {seed_applications(db, data_dir, 'eval')}")


if __name__ == "__main__":
    main()
