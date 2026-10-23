"""Document content (audited view) and the extraction interface (FR-3, FR-9)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import COMPLIANCE_OFFICER, KYC_OFFICER, CurrentUser, current_user, get_application_for, require_roles
from app.db import get_db
from app.errors import ApiError
from app.models import Document
from app.services import audit
from app.services.extraction import get_provider
from app.services.workflow import read_text

router = APIRouter(prefix="/documents", tags=["documents"])


def _document_for(db: Session, doc_id: str, user: CurrentUser) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document not found")
    get_application_for(db, doc.application_id, user)   # ownership / staff check, 404 otherwise
    return doc


@router.get("/{doc_id}/content")
def document_content(doc_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)) -> dict:
    """Every view of a document is written to the audit trail (who, role, when)."""
    doc = _document_for(db, doc_id, user)
    role = KYC_OFFICER if KYC_OFFICER in user.roles else (COMPLIANCE_OFFICER if user.is_staff else "APPLICANT")
    audit.log(db, action="DOCUMENT_VIEWED", entity="DOCUMENT", entity_id=doc.id,
              application_id=doc.application_id, actor=(user.id, role))
    db.commit()
    return {"doc_id": doc.id, "doc_ref": doc.doc_ref, "file_name": doc.file_name,
            "declared_doc_type": doc.declared_doc_type, "text": read_text(doc)}


@router.post("/{doc_id}/extract")
def extract(doc_id: str, db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_roles(KYC_OFFICER, COMPLIANCE_OFFICER))) -> dict:
    """FR-3: run the configured provider on one document and return the long format (read-only)."""
    doc = _document_for(db, doc_id, user)
    res = get_provider(db).extract(doc.doc_ref, read_text(doc))
    return {"doc_id": doc.id, "doc_ref": doc.doc_ref, "provider": res.provider, "doc_type": res.doc_type,
            "doc_type_confidence": res.doc_type_confidence,
            "fields": [{"field_name": n, "value": v, "confidence": c} for n, v, c in res.fields],
            "long_format": res.as_long_format(doc.doc_ref)}
