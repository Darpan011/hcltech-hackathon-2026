"""API tests for the security and workflow requirements (FR-1..FR-11, NFR concurrency)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from app.cli.seed import seed_applications, seed_reference, seed_users
from app.db import Base, SessionLocal, create_tables, engine
from app.main import app
from app.models import Application, AuditLog, Document
from app.services import datapack, workflow
from app.settings import settings

DATA = settings.data_dir
TEXTS = {d["doc_id"]: d["text"] for d in datapack.read_jsonl(datapack.path(DATA, "text_sample"))}
RAVI = {  # example 1 applicant (A2000001)
    "full_name": "Ravi Kumar Sharma", "dob": "1990-05-15", "gender": "M", "pan_number": "ZZKPS1234Q",
    "aadhaar_last4": "4821", "mobile": "9876500000", "email": "ravi@example.com",
    "address": "Flat 12, Lotus Residency, MG Road, Mumbai, Maharashtra", "city": "Mumbai",
    "state": "Maharashtra", "pincode": "400001", "occupation_code": "SALARIED_PRIVATE",
    "annual_income": 900000, "consent": True,
}
RAVI_DOCS = [("D3000001", "PAN_CARD"), ("D3000002", "AADHAAR_CARD"), ("D3000003", "ELECTRICITY_BILL")]


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(engine)
    create_tables()
    with SessionLocal() as db:
        seed_reference(db, DATA)
        seed_users(db)
        seed_applications(db, DATA, "sample")
    with TestClient(app) as c:
        yield c


def login(c, username: str) -> dict:
    r = c.post("/api/v1/auth/login", json={"username": username, "password": settings.seed_password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def upload(c, h, app_id, doc_id, declared):
    return c.post(f"/api/v1/applications/{app_id}/documents", headers=h,
                  files={"file": (f"{doc_id}.txt", TEXTS[doc_id].encode(), "text/plain")},
                  data={"declared_doc_type": declared})


def new_application(c, h, body=RAVI, docs=RAVI_DOCS) -> str:
    r = c.post("/api/v1/applications", headers=h, json=body)
    assert r.status_code == 201, r.text
    app_id = r.json()["application_id"]
    for doc_id, declared in docs:
        assert upload(c, h, app_id, doc_id, declared).status_code == 201
    return app_id


def version_of(c, h, app_id) -> int:
    return c.get(f"/api/v1/applications/{app_id}", headers=h).json()["version"]


# ---------- authentication and access (FR-1) ----------

def test_no_token_is_401(client):
    r = client.get("/api/v1/applications/mine")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_wrong_password_is_401(client):
    r = client.post("/api/v1/auth/login", json={"username": "officer1", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_applicant_on_officer_api_is_403(client):
    r = client.get("/api/v1/review/queue", headers=login(client, "applicant_demo"))
    assert r.status_code == 403


def test_other_applicant_cannot_see_application(client):
    client.post("/api/v1/auth/register", json={"username": "stranger", "password": "Stranger@123",
                                               "full_name": "Some Stranger"})
    tok = client.post("/api/v1/auth/login", json={"username": "stranger", "password": "Stranger@123"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get("/api/v1/applications/A2000001", headers=h).status_code == 404


# ---------- validation (FR-2) ----------

def test_twelve_digit_aadhaar_is_refused(client):
    r = client.post("/api/v1/applications", headers=login(client, "applicant_demo"),
                    json={**RAVI, "aadhaar_last4": "1234 5678 4821"})
    assert r.status_code == 422
    field = r.json()["error"]["fields"][0]
    assert field["field"] == "aadhaar_last4" and "12-digit" in field["message"]


def test_upload_rules_and_duplicate(client):
    h = login(client, "applicant_demo")
    app_id = client.post("/api/v1/applications", headers=h, json=RAVI).json()["application_id"]
    bad = client.post(f"/api/v1/applications/{app_id}/documents", headers=h,
                      files={"file": ("scan.pdf", b"%PDF", "application/pdf")}, data={"declared_doc_type": "PAN_CARD"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_FILE"
    assert upload(client, h, app_id, "D3000001", "PAN_CARD").status_code == 201
    dup = upload(client, h, app_id, "D3000001", "PAN_CARD")
    assert dup.status_code == 200 and dup.json()["duplicate"] is True
    with SessionLocal() as db:
        assert len(db.scalars(select(Document).where(Document.application_id == app_id)).all()) == 1
    r = client.post(f"/api/v1/applications/{app_id}/submit", headers=h)
    assert r.status_code == 422          # fewer than 3 documents


# ---------- straight-through processing (FR-3, FR-4, example 1) ----------

def test_clean_application_is_auto_approved_with_account(client):
    h = login(client, "applicant_demo")
    app_id = new_application(client, h)
    r = client.post(f"/api/v1/applications/{app_id}/submit", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "AUTO_APPROVED" and body["account_no"] and body["reasons"] == []
    assert "confidence" not in str(body)            # applicant never sees confidence scores
    staff = client.get(f"/api/v1/applications/{app_id}", headers=login(client, "officer1")).json()
    assert staff["decision"] == "APPROVE" and staff["name_match_score"] == 1.0
    assert {d["doc_type"] for d in staff["documents"]} == {"PAN_CARD", "AADHAAR_CARD", "ELECTRICITY_BILL"}


def test_extract_endpoint_and_unknown_document(client):
    h = login(client, "applicant_demo")
    app_id = client.post("/api/v1/applications", headers=h, json=RAVI).json()["application_id"]
    doc = client.post(f"/api/v1/applications/{app_id}/documents", headers=h,
                      files={"file": ("my_notes.txt", b"hello", "text/plain")},
                      data={"declared_doc_type": "PAN_CARD"}).json()
    r = client.post(f"/api/v1/documents/{doc['doc_id']}/extract", headers=login(client, "officer1"))
    assert r.status_code == 200
    assert (r.json()["doc_type"], r.json()["doc_type_confidence"]) == ("OTHER", 0.0)


# ---------- maker-checker (FR-7, examples 10 and 11) ----------

def test_example_10_high_risk_approve_waits_for_checker(client):
    r = client.get("/api/v1/applications/A2000010", headers=login(client, "checker1")).json()
    assert r["status"] == "PENDING_CHECKER" and r["risk_category"] == "HIGH"


def test_example_11_maker_cannot_check_then_checker_approves(client):
    dual = login(client, "officer_checker")
    v = version_of(client, dual, "A2000004")
    r = client.post("/api/v1/applications/A2000004/recommend", headers=dual,
                    json={"action": "APPROVE", "comment": "Name variant verified on Aadhaar", "version": v})
    assert r.status_code == 200 and r.json()["status"] == "PENDING_CHECKER"
    r = client.post("/api/v1/applications/A2000004/check", headers=dual,
                    json={"action": "APPROVE", "comment": "Approving my own case", "version": r.json()["version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "MAKER_CANNOT_CHECK"
    checker = login(client, "checker1")
    r = client.post("/api/v1/applications/A2000004/check", headers=checker,
                    json={"action": "APPROVE", "comment": "Evidence checked, approving",
                          "version": version_of(client, checker, "A2000004")})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED" and r.json()["account_no"]


def test_stale_version_is_409(client):
    h = login(client, "officer1")
    r = client.post("/api/v1/applications/A2000005/recommend", headers=h,
                    json={"action": "APPROVE", "comment": "Old screen data here", "version": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_concurrent_update_loses_optimistic_lock():
    """Two officers load the same case; the second write must fail (-> HTTP 409 via StaleDataError)."""
    with SessionLocal() as s1, SessionLocal() as s2:
        a1, a2 = s1.get(Application, "A2000017"), s2.get(Application, "A2000017")
        workflow.recommend(s1, a1, ("U1", "KYC_OFFICER"), "APPROVE", "First officer wins", a1.version)
        s1.commit()
        with pytest.raises(StaleDataError):
            workflow.recommend(s2, a2, ("U3", "KYC_OFFICER"), "REJECT", "Second officer loses", a2.version)
        s2.rollback()


# ---------- correction (FR-6, example 12) ----------

def test_example_12_correction_reruns_rules_and_is_audited(client):
    h = login(client, "officer1")
    review = client.get("/api/v1/applications/A2000009/review", headers=h).json()
    assert review["decision"]["reason_codes"] == ["LOW_EXTRACTION_CONFIDENCE"]
    pan_doc = next(d for d in review["documents"] if d["selected_as"] == "PAN_CARD")
    low = next(f for f in pan_doc["fields"] if f["field_name"] == "pan_number")
    assert low["usable"] is False and low["value"] == "ZZTP59O12Y"
    r = client.patch("/api/v1/applications/A2000009/fields", headers=h, json={
        "doc_id": pan_doc["doc_id"], "field_name": "pan_number", "value": "ZZTPS9012Y",
        "reason": "Read from the document text: OCR misread S as 5 and 0 as O",
        "version": review["application"]["version"]})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["decision"]["decision"] == "APPROVE" and after["decision"]["reason_codes"] == []
    assert after["application"]["status"] == "IN_REVIEW"          # still needs maker-checker
    with SessionLocal() as db:
        row = db.scalar(select(AuditLog).where(AuditLog.application_id == "A2000009",
                                               AuditLog.action == "FIELD_CORRECTED"))
        assert row.before["value"] == "ZZTP59O12Y" and row.after["value"] == "ZZTPS9012Y"
    r = client.post("/api/v1/applications/A2000009/recommend", headers=h,
                    json={"action": "APPROVE", "comment": "PAN corrected, all checks pass",
                          "version": after["application"]["version"]})
    assert r.json()["status"] == "PENDING_CHECKER"


def test_document_view_is_audited(client):
    h = login(client, "officer1")
    doc_id = client.get("/api/v1/applications/A2000003/review", headers=h).json()["documents"][0]["doc_id"]
    assert "SYNTHETIC SPECIMEN" in client.get(f"/api/v1/documents/{doc_id}/content", headers=h).json()["text"]
    with SessionLocal() as db:
        views = db.scalars(select(AuditLog).where(AuditLog.entity_id == doc_id,
                                                  AuditLog.action == "DOCUMENT_VIEWED")).all()
        assert views and views[-1].actor_id == "U1"


# ---------- config (FR-4) ----------

def test_config_change_changes_next_decision(client):
    checker, applicant = login(client, "checker1"), login(client, "applicant_demo")
    bad = client.put("/api/v1/config/name_match_threshold", headers=checker, json={"value": 7})
    assert bad.status_code == 422
    assert client.put("/api/v1/config/name_match_threshold", headers=checker, json={"value": 0.75}).status_code == 200
    try:
        body = {**RAVI, "dob": "1992-01-20", "pan_number": "ZZNPS4567T", "aadhaar_last4": "7781"}
        app_id = new_application(client, applicant, body, [("D3000010", "PAN_CARD"), ("D3000011", "AADHAAR_CARD"),
                                                           ("D3000012", "ELECTRICITY_BILL")])
        r = client.post(f"/api/v1/applications/{app_id}/submit", headers=applicant).json()
        assert r["status"] == "AUTO_APPROVED"          # example 4 data, 0.7647 now passes
    finally:
        client.put("/api/v1/config/name_match_threshold", headers=checker, json={"value": 0.9})


# ---------- resubmission + expiry (FR-8) ----------

def test_resubmission_then_reevaluated(client):
    officer, applicant = login(client, "officer1"), login(client, "applicant_demo")
    r = client.post("/api/v1/applications/A2000005/recommend", headers=officer,
                    json={"action": "REQUEST_RESUBMISSION", "comment": "Please upload a recent electricity bill",
                          "version": version_of(client, officer, "A2000005")})
    assert r.json()["status"] == "RESUBMISSION_REQUESTED"
    view = client.get("/api/v1/applications/A2000005", headers=applicant).json()
    assert view["can_upload"] and view["resubmission_due_at"]
    assert upload(client, applicant, "A2000005", "D3000003", "ELECTRICITY_BILL").status_code == 201
    r = client.post("/api/v1/applications/A2000005/submit", headers=applicant).json()
    assert r["status"] == "AUTO_APPROVED"


def test_expired_resubmission_is_closed(client):
    officer = login(client, "officer1")
    client.post("/api/v1/applications/A2000060/recommend", headers=officer,
                json={"action": "REQUEST_RESUBMISSION", "comment": "Please upload a recent bank statement",
                      "version": version_of(client, officer, "A2000060")})
    with SessionLocal() as db:
        a = db.get(Application, "A2000060")
        a.resubmission_due_at = a.resubmission_due_at.replace(year=2020)
        db.commit()
    r = client.get("/api/v1/applications/A2000060", headers=login(client, "applicant_demo")).json()
    assert r["status"] == "CLOSED_EXPIRED"


# ---------- dashboard + audit (FR-9, FR-10) ----------

def test_dashboard_reconciles(client):
    d = client.get("/api/v1/dashboard", headers=login(client, "checker1")).json()
    assert sum(d["by_status"].values()) == d["total_applications"]
    assert 0 < d["straight_through_rate"] <= 1 and len(d["top_reason_codes"]) <= 5


def test_audit_export_masks_pan(client):
    r = client.get("/api/v1/applications/A2000009/audit/export", headers=login(client, "checker1"))
    assert r.status_code == 200 and "FIELD_CORRECTED" in r.text
    assert "ZZTPS9012Y" not in r.text and "ZZTXXXXX2Y" in r.text


def test_officer_cannot_read_audit(client):
    assert client.get("/api/v1/applications/A2000001/audit", headers=login(client, "officer1")).status_code == 403


# ---------- "Sign in as" role dropdown ----------

def _login_as(c, username, role):
    return c.post("/api/v1/auth/login", json={"username": username, "password": settings.seed_password, "role": role})


def test_sign_in_with_a_role_the_account_lacks_is_403(client):
    r = _login_as(client, "officer1", "COMPLIANCE_OFFICER")
    assert r.status_code == 403 and r.json()["error"]["code"] == "ROLE_NOT_ASSIGNED"
    assert _login_as(client, "applicant_demo", "KYC_AND_COMPLIANCE").status_code == 403


def test_session_carries_only_the_chosen_role(client):
    r = _login_as(client, "officer_checker", "KYC_OFFICER")
    assert r.status_code == 200 and r.json()["user"]["roles"] == ["KYC_OFFICER"]
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/review/queue", headers=h).status_code == 200
    assert client.get("/api/v1/checker/queue", headers=h).status_code == 403   # compliance not active


def test_dual_role_sign_in(client):
    r = _login_as(client, "officer_checker", "KYC_AND_COMPLIANCE")
    assert r.status_code == 200 and set(r.json()["user"]["roles"]) == {"KYC_OFFICER", "COMPLIANCE_OFFICER"}
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/checker/queue", headers=h).status_code == 200


def test_unknown_role_value_is_422(client):
    assert _login_as(client, "officer1", "ADMIN").status_code == 422


# ---------- Branch onboarding (SELF_SERVICE_ONBOARDING=false) ----------

@pytest.fixture
def branch_mode(monkeypatch):
    monkeypatch.setattr(settings, "self_service_onboarding", False)


def test_branch_mode_blocks_self_registration_and_self_apply(client, branch_mode):
    r = client.post("/api/v1/auth/register", json={"username": "walkin_x", "password": "Walkin@123", "full_name": "W X"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_REGISTRATION_DISABLED"
    r = client.post("/api/v1/applications", headers=login(client, "applicant_demo"), json=RAVI)
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_SERVICE_DISABLED"
    assert client.get("/api/v1/auth/config").json() == {"self_service_onboarding": False}


def test_officer_onboards_walk_in_customer_who_can_then_sign_in(client, branch_mode):
    officer = login(client, "officer1")
    r = client.post("/api/v1/branch/applications", headers=officer, json={**RAVI, "username": "ravi_walkin"})
    assert r.status_code == 201, r.text
    app_id, creds = r.json()["application_id"], r.json()["customer"]
    for doc_id, declared in RAVI_DOCS:
        up = client.post(f"/api/v1/branch/applications/{app_id}/documents", headers=officer,
                         files={"file": (f"{doc_id}.txt", TEXTS[doc_id].encode(), "text/plain")},
                         data={"declared_doc_type": declared})
        assert up.status_code == 201
    r = client.post(f"/api/v1/branch/applications/{app_id}/submit", headers=officer)
    assert r.status_code == 200 and r.json()["status"] == "AUTO_APPROVED"
    # the customer can now sign in with the credentials the officer handed over, and sees only their case
    tok = client.post("/api/v1/auth/login", json={"username": creds["username"], "password": creds["temporary_password"],
                                                  "role": "APPLICANT"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    mine = client.get("/api/v1/applications/mine", headers=h).json()
    assert [a["application_id"] for a in mine] == [app_id]
    assert client.get(f"/api/v1/applications/{app_id}", headers=h).json()["status"] == "AUTO_APPROVED"


def test_unknown_person_cannot_sign_in(client, branch_mode):
    r = client.post("/api/v1/auth/login", json={"username": "nobody_here", "password": "Whatever@1", "role": "APPLICANT"})
    assert r.status_code == 401


def test_data_entry_officer_cannot_review_own_entry(client, branch_mode):
    officer1, officer2 = login(client, "officer1"), login(client, "officer2")
    body = {**RAVI, "dob": "1992-01-20", "pan_number": "ZZNPS4567T", "aadhaar_last4": "7781"}
    app_id = client.post("/api/v1/branch/applications", headers=officer1, json=body).json()["application_id"]
    for doc_id, declared in [("D3000010", "PAN_CARD"), ("D3000011", "AADHAAR_CARD"), ("D3000012", "ELECTRICITY_BILL")]:
        client.post(f"/api/v1/branch/applications/{app_id}/documents", headers=officer1,
                    files={"file": (f"{doc_id}.txt", TEXTS[doc_id].encode(), "text/plain")},
                    data={"declared_doc_type": declared})
    assert client.post(f"/api/v1/branch/applications/{app_id}/submit", headers=officer1).json()["status"] == "IN_REVIEW"
    v = version_of(client, officer1, app_id)
    r = client.post(f"/api/v1/applications/{app_id}/recommend", headers=officer1,
                    json={"action": "APPROVE", "comment": "Approving data I entered myself", "version": v})
    assert r.status_code == 403 and r.json()["error"]["code"] == "DATA_ENTRY_CANNOT_REVIEW"
    r = client.post(f"/api/v1/applications/{app_id}/recommend", headers=officer2,
                    json={"action": "APPROVE", "comment": "Second officer verified the name", "version": v})
    assert r.status_code == 200 and r.json()["status"] == "PENDING_CHECKER"


def test_branch_endpoints_are_officer_only(client, branch_mode):
    r = client.post("/api/v1/branch/applications", headers=login(client, "applicant_demo"), json=RAVI)
    assert r.status_code == 403
