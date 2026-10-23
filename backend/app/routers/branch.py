"""Branch onboarding: a KYC Officer enters a walk-in customer's data and documents,
and the system creates the customer's login. Only customers entered here can sign in."""
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import APPLICANT, KYC_OFFICER, CurrentUser, hash_password, require_roles
from app.db import get_db
from app.errors import ApiError
from app.models import Application, AuditLog, Occupation, User
from app.schemas import ApplicationCreate
from app.services import audit, workflow
from app.views import decision_view, staff_application, summary

router = APIRouter(prefix="/branch", tags=["branch onboarding"])
officer = require_roles(KYC_OFFICER)


class BranchApplicationIn(ApplicationCreate):
    username: str | None = Field(default=None, min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_.]+$")


def _branch_app(db: Session, application_id: str) -> Application:
    app = db.get(Application, application_id)
    if app is None or app.source != "BRANCH":
        raise ApiError(404, "NOT_FOUND", "Branch application not found")
    return app


def _username_for(db: Session, wanted: str | None, full_name: str) -> str:
    if wanted:
        name = wanted.lower()
        if db.scalar(select(User).where(User.username == name)):
            raise ApiError(409, "USERNAME_TAKEN", "That username is already taken",
                           [{"field": "username", "message": "Choose another username"}])
        return name
    base = (re.sub(r"[^a-z]", "", full_name.lower().split()[0]) or "customer")[:12]
    while True:
        name = f"{base}{secrets.randbelow(9000) + 1000}"
        if not db.scalar(select(User).where(User.username == name)):
            return name


@router.post("/applications", status_code=201)
def create_branch_application(body: BranchApplicationIn, db: Session = Depends(get_db),
                              user: CurrentUser = Depends(officer)) -> dict:
    """Officer enters the customer's form; creates the customer's login with a one-time password."""
    if db.get(Occupation, body.occupation_code) is None:
        raise ApiError(422, "VALIDATION_ERROR", "Request has invalid fields",
                       [{"field": "occupation_code", "message": "Unknown occupation"}])
    actor = (user.id, KYC_OFFICER)
    username = _username_for(db, body.username, body.full_name)
    temp_password = f"Kyc-{secrets.token_hex(3)}-{secrets.token_hex(2)}"   # shown once, handed to the customer
    customer = User(id=f"U{uuid.uuid4().hex[:8]}", username=username, full_name=body.full_name,
                    roles=APPLICANT, password_hash=hash_password(temp_password))
    db.add(customer)
    db.flush()
    audit.log(db, action="USER_CREATED_AT_BRANCH", entity="USER", entity_id=customer.id, actor=actor,
              after={"username": username})
    fields = body.model_dump(exclude={"username"})
    app = Application(application_id=workflow.new_application_id(db), owner_id=customer.id, source="BRANCH",
                      application_date=workflow.business_today(), status="DRAFT", **fields)
    db.add(app)
    db.flush()
    audit.log(db, action="APPLICATION_CREATED", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=actor, to_status="DRAFT", comment="Entered at branch")
    db.commit()
    return {"application_id": app.application_id, "status": app.status, "version": app.version,
            "customer": {"user_id": customer.id, "username": username, "temporary_password": temp_password}}


@router.get("/applications")
def my_branch_applications(db: Session = Depends(get_db), user: CurrentUser = Depends(officer)) -> list:
    """Applications this officer entered at the branch, newest first."""
    ids = db.scalars(select(AuditLog.application_id).where(AuditLog.action == "APPLICATION_CREATED",
                                                           AuditLog.actor_id == user.id)).all()
    apps = db.scalars(select(Application).where(Application.application_id.in_(ids), Application.source == "BRANCH")
                      .order_by(Application.created_at.desc())).all() if ids else []
    return [summary(a) for a in apps]


@router.get("/applications/{application_id}")
def get_branch_application(application_id: str, db: Session = Depends(get_db),
                           user: CurrentUser = Depends(officer)) -> dict:
    app = _branch_app(db, application_id)
    docs = [{"doc_id": d.id, "file_name": d.file_name, "declared_doc_type": d.declared_doc_type,
             "superseded": d.superseded, "uploaded_at": d.uploaded_at} for d in app.documents]
    owner = db.get(User, app.owner_id)
    return {**decision_view(app), "application": staff_application(app), "uploaded": docs,
            "customer_username": owner.username if owner else None,
            "entered_by": workflow.entered_by(db, app),
            "can_upload": app.status in ("DRAFT", "RESUBMISSION_REQUESTED"),
            "can_submit": app.status in ("DRAFT", "RESUBMISSION_REQUESTED")
            and len(workflow.active_documents(app)) >= 3}


@router.post("/applications/{application_id}/documents", status_code=201)
async def upload_at_branch(application_id: str, file: UploadFile = File(...), declared_doc_type: str = Form(...),
                           db: Session = Depends(get_db), user: CurrentUser = Depends(officer)):
    app = _branch_app(db, application_id)
    content = await file.read(workflow.MAX_UPLOAD_BYTES + 1)
    doc, duplicate = workflow.add_document(db, app, (user.id, KYC_OFFICER), file.filename or "",
                                           content, declared_doc_type)
    db.commit()
    return JSONResponse({"doc_id": doc.id, "doc_ref": doc.doc_ref, "file_name": doc.file_name,
                         "declared_doc_type": doc.declared_doc_type, "duplicate": duplicate},
                        status_code=200 if duplicate else 201)


@router.post("/applications/{application_id}/submit")
def submit_at_branch(application_id: str, db: Session = Depends(get_db),
                     user: CurrentUser = Depends(officer)) -> dict:
    """Same submit -> extract -> rules -> route workflow as online applications."""
    app = _branch_app(db, application_id)
    workflow.submit(db, app, (user.id, KYC_OFFICER))
    db.commit()
    return {**decision_view(app), "application": staff_application(app)}
