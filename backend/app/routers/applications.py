"""Applicant endpoints + application detail (FR-2, FR-8)."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import APPLICANT, CurrentUser, current_user, get_application_for, require_roles
from app.db import get_db
from app.errors import ApiError
from app.models import Application, Occupation
from app.schemas import ApplicationCreate
from app.services import audit, workflow
from app.settings import settings
from app.views import applicant_view, decision_view, staff_application, summary

router = APIRouter(prefix="/applications", tags=["applications"])


def _owner_only(app: Application, user: CurrentUser) -> None:
    if app.owner_id != user.id:
        raise ApiError(404, "NOT_FOUND", "Application not found")


@router.post("", status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(require_roles(APPLICANT))) -> dict:
    if not settings.self_service_onboarding:
        raise ApiError(403, "SELF_SERVICE_DISABLED",
                       "New applications are opened at the branch by a KYC Officer.")
    if db.get(Occupation, body.occupation_code) is None:
        raise ApiError(422, "VALIDATION_ERROR", "Request has invalid fields",
                       [{"field": "occupation_code", "message": "Unknown occupation"}])
    app = Application(application_id=workflow.new_application_id(db), owner_id=user.id, source="UI",
                      application_date=workflow.business_today(), status="DRAFT", **body.model_dump())
    db.add(app)
    db.flush()
    audit.log(db, action="APPLICATION_CREATED", entity="APPLICATION", entity_id=app.application_id,
              application_id=app.application_id, actor=(user.id, APPLICANT), to_status="DRAFT")
    db.commit()
    return {"application_id": app.application_id, "status": app.status, "version": app.version}


@router.get("/mine")
def my_applications(db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles(APPLICANT))) -> list:
    apps = db.scalars(select(Application).where(Application.owner_id == user.id)
                      .order_by(Application.created_at.desc()))
    return [{k: v for k, v in summary(a).items() if k in ("application_id", "full_name", "status",
                                                          "application_date", "submitted_at", "version")}
            for a in apps]


@router.get("/{application_id}")
def get_application(application_id: str, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(current_user)) -> dict:
    app = get_application_for(db, application_id, user)
    if workflow.expire_if_due(db, app):
        db.commit()
    if user.is_staff:
        return {**decision_view(app), "application": staff_application(app)}
    return applicant_view(db, app)


@router.post("/{application_id}/documents", status_code=201)
async def upload_document(application_id: str, file: UploadFile = File(...),
                          declared_doc_type: str = Form(...), db: Session = Depends(get_db),
                          user: CurrentUser = Depends(require_roles(APPLICANT))):
    app = get_application_for(db, application_id, user)
    _owner_only(app, user)
    content = await file.read(workflow.MAX_UPLOAD_BYTES + 1)
    doc, duplicate = workflow.add_document(db, app, (user.id, APPLICANT), file.filename or "",
                                           content, declared_doc_type)
    db.commit()
    body = {"doc_id": doc.id, "doc_ref": doc.doc_ref, "file_name": doc.file_name,
            "declared_doc_type": doc.declared_doc_type, "sha256": doc.sha256, "size_bytes": doc.size_bytes,
            "duplicate": duplicate}
    return JSONResponse(body, status_code=200 if duplicate else 201)


@router.get("/{application_id}/documents")
def list_documents(application_id: str, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(current_user)) -> list:
    app = get_application_for(db, application_id, user)
    return [{"doc_id": d.id, "doc_ref": d.doc_ref, "file_name": d.file_name,
             "declared_doc_type": d.declared_doc_type, "superseded": d.superseded,
             "uploaded_at": d.uploaded_at} for d in app.documents]


@router.post("/{application_id}/submit")
def submit(application_id: str, db: Session = Depends(get_db),
           user: CurrentUser = Depends(require_roles(APPLICANT))) -> dict:
    app = get_application_for(db, application_id, user)
    _owner_only(app, user)
    workflow.submit(db, app, (user.id, APPLICANT))
    db.commit()
    return applicant_view(db, app)
