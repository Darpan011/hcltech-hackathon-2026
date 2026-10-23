"""SQLAlchemy models (design §5)."""
import uuid
from datetime import date, datetime

from sqlalchemy import (DDL, JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        Numeric, String, Text, UniqueConstraint, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.services.dates import now_ist

JsonType = JSON().with_variant(JSONB(), "postgresql")
BigId = BigInteger().with_variant(Integer(), "sqlite")   # SQLite autoincrement needs INTEGER


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=now_ist)


# ---------- users and reference data ----------

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(100))
    roles: Mapped[str] = mapped_column(String(100))            # comma-separated
    created_at: Mapped[datetime] = _ts()

    @property
    def role_list(self) -> list[str]:
        return [r for r in self.roles.split(",") if r]


class ConfigEntry(Base):
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JsonType)
    updated_at: Mapped[datetime] = _ts()


class Occupation(Base):
    __tablename__ = "occupations"
    occupation_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(100))
    risk_level: Mapped[str] = mapped_column(String(10))


class SanctionsEntry(Base):
    __tablename__ = "watchlist_sanctions"
    list_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    alias: Mapped[str] = mapped_column(String(100), default="")
    dob: Mapped[str] = mapped_column(String(10), default="")
    nationality: Mapped[str] = mapped_column(String(10), default="")
    program: Mapped[str] = mapped_column(String(60), default="")


class PepEntry(Base):
    __tablename__ = "watchlist_pep"
    pep_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    dob: Mapped[str] = mapped_column(String(10), default="")
    position: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(20), default="")


class ExistingCustomer(Base):
    __tablename__ = "existing_customers"
    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    pan_number: Mapped[str] = mapped_column(String(10), index=True)
    dob: Mapped[str] = mapped_column(String(10))


class MockExtraction(Base):
    """The supplied extraction_mock files, in their long format."""
    __tablename__ = "mock_extraction"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(40), index=True)
    field_name: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)


class AppSequence(Base):
    """Source of new application numbers (A9000001, A9000002, ...)."""
    __tablename__ = "app_sequence"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)


# ---------- applications ----------

class Application(Base):
    __tablename__ = "applications"
    application_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(10), default="UI")        # UI | SEED
    application_date: Mapped[date] = mapped_column(Date)
    full_name: Mapped[str] = mapped_column(String(100))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(1))
    pan_number: Mapped[str] = mapped_column(String(10))
    aadhaar_last4: Mapped[str] = mapped_column(String(4))
    mobile: Mapped[str] = mapped_column(String(10))
    email: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(300))
    city: Mapped[str] = mapped_column(String(60))
    state: Mapped[str] = mapped_column(String(60))
    pincode: Mapped[str] = mapped_column(String(6))
    occupation_code: Mapped[str] = mapped_column(ForeignKey("occupations.occupation_code"))
    annual_income: Mapped[float] = mapped_column(Numeric(14, 2))
    consent: Mapped[bool] = mapped_column(Boolean)

    status: Mapped[str] = mapped_column(String(30), index=True, default="DRAFT")
    decision: Mapped[str | None] = mapped_column(String(10))
    reason_codes: Mapped[str] = mapped_column(String(500), default="")
    name_match_score: Mapped[float | None] = mapped_column(Float)
    risk_category: Mapped[str | None] = mapped_column(String(10))
    rekyc_due_date: Mapped[date | None] = mapped_column(Date)
    maker_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    maker_action: Mapped[str | None] = mapped_column(String(30))
    customer_id: Mapped[str | None] = mapped_column(String(20))
    account_no: Mapped[str | None] = mapped_column(String(20))
    resubmission_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)

    documents: Mapped[list["Document"]] = relationship(back_populates="application", order_by="Document.doc_ref")

    # Optimistic locking: every UPDATE includes "WHERE version = <loaded>" and bumps it;
    # a concurrent change makes the UPDATE hit 0 rows -> StaleDataError -> HTTP 409.
    __mapper_args__ = {"version_id_col": version}


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("application_id", "sha256", name="uq_document_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.application_id"), index=True)
    doc_ref: Mapped[str] = mapped_column(String(40))          # file-name stem, e.g. D3000001
    file_name: Mapped[str] = mapped_column(String(255))
    declared_doc_type: Mapped[str] = mapped_column(String(30))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = _ts()

    application: Mapped[Application] = relationship(back_populates="documents")
    fields: Mapped[list["ExtractedField"]] = relationship(back_populates="document", order_by="ExtractedField.id")


class ExtractedField(Base):
    """Same long format as the mock file. Corrections add a row; the old row stays (is_current=False)."""
    __tablename__ = "extracted_fields"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(10))           # MOCK | OFFICER
    provider: Mapped[str] = mapped_column(String(20))
    corrected_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _ts()

    document: Mapped[Document] = relationship(back_populates="fields")


class RuleResult(Base):
    """Every rules run is kept (run 1 on submit, run 2 after a correction, ...)."""
    __tablename__ = "rule_results"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.application_id"), index=True)
    run_no: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(20))           # SUBMIT | CORRECTION
    decision: Mapped[str] = mapped_column(String(10))
    reason_codes: Mapped[str] = mapped_column(String(500), default="")
    name_match_score: Mapped[float | None] = mapped_column(Float)
    risk_category: Mapped[str | None] = mapped_column(String(10))
    rekyc_due_date: Mapped[date | None] = mapped_column(Date)
    details: Mapped[object] = mapped_column(JsonType)
    selected: Mapped[object] = mapped_column(JsonType)
    created_at: Mapped[datetime] = _ts()


class ScreeningHitRow(Base):
    __tablename__ = "screening_hits"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.application_id"), index=True)
    run_no: Mapped[int] = mapped_column(Integer)
    list_type: Mapped[str] = mapped_column(String(10))
    entry_id: Mapped[str] = mapped_column(String(20))
    entry_name: Mapped[str] = mapped_column(String(100))
    matched_on: Mapped[str] = mapped_column(String(10))
    similarity: Mapped[float] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(10))
    dob_comparison: Mapped[str] = mapped_column(String(20))
    list_dob: Mapped[str] = mapped_column(String(10), default="")


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.application_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class AuditLog(Base):
    """Append-only (enforced by a database trigger, see below)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = _ts()
    entity: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(64))
    application_id: Mapped[str | None] = mapped_column(String(12), index=True)
    actor_id: Mapped[str] = mapped_column(String(20))
    actor_role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    before: Mapped[object | None] = mapped_column(JsonType)
    after: Mapped[object | None] = mapped_column(JsonType)
    comment: Mapped[str | None] = mapped_column(Text)


# The database itself refuses UPDATE/DELETE on audit rows, even if application code had a bug.
event.listen(AuditLog.__table__, "after_create", DDL("""
CREATE OR REPLACE FUNCTION audit_no_change() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_no_change();
""").execute_if(dialect="postgresql"))
event.listen(AuditLog.__table__, "after_create", DDL(
    "CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;"
).execute_if(dialect="sqlite"))
event.listen(AuditLog.__table__, "after_create", DDL(
    "CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;"
).execute_if(dialect="sqlite"))
