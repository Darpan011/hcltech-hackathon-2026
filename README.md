# OnboardIQ — KYC Onboarding (HCLTech Hackathon, Use Case 02, core track)

React (Vite) · FastAPI · PostgreSQL · Kafka (notifications only) · Docker Compose
Design: `output/design/design_document.md` · API docs: http://localhost:8000/docs

## Quick start

```bash
cp .env.example .env          # replace every change_me (JWT_SECRET, CORE_BANKING_KEY, POSTGRES_PASSWORD)
docker compose up --build     # first start seeds reference data, demo users and the 60 sample applications
```

| What | URL / command |
|---|---|
| App | http://localhost:5173 |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/api/v1/health |
| Notifications (Kafka consumer) | `docker compose logs -f notifier` |
| Reset demo data | `docker compose exec backend python -m app.cli.seed --reset --with-sample-apps` |

### Demo logins (password `Demo@123`, set by `SEED_PASSWORD`)

| Username | Role |
|---|---|
| `applicant_demo` | Applicant (owns the 60 seeded sample applications) |
| `officer1`, `officer2` | KYC Officer (maker) |
| `checker1`, `checker2` | Compliance Officer (checker) |
| `officer_checker` | both roles: shows maker ≠ checker (403) |

Documents to upload are written to `data/upload_demo/<doc_id>.txt` by the seed
(e.g. D3000001 PAN, D3000002 Aadhaar, D3000003 electricity bill = worked example 1).

## Onboarding modes (`SELF_SERVICE_ONBOARDING`)

| Value | Flow |
|---|---|
| `false` (default) | **Branch onboarding.** Customer visits the branch → KYC Officer → *Branch intake* → enters details, uploads the scanned documents, submits → system creates the customer's login (one-time password shown once). Only customers entered by the bank can sign in; self-registration and online "New application" are off. The officer who entered a customer cannot review that case; another officer must. |
| `true` | **Online self-service** (original flow): applicants register, apply and upload themselves. |

Rules, review, maker-checker, audit and batch are identical in both modes.

## Batch outputs (FR-11)

```bash
docker compose exec backend python -m app.cli.batch --set sample --compare   # 60/60 must match
docker compose exec backend python -m app.cli.batch --set eval               # -> /output/decisions_output.csv
# explicit files:
python -m app.cli.batch --applications A.csv --documents D.csv --extraction E.csv --out out.csv
```

The batch reads reference data straight from the data-pack files, so it runs without the database.

## Tests

```bash
docker compose exec backend pytest -q          # 48 tests: 60 sample rows, worked examples, API security + workflow
# locally without Docker (uses a temporary SQLite DB; TEST_DATABASE_URL=postgresql+psycopg://... to use Postgres)
cd backend && pip install -r requirements.txt && pytest -q
```

## Demo script (worked examples)

1. **Example 1 (straight-through):** log in as `applicant_demo` → New application → *Fill demo data* → upload
   D3000001 (PAN card), D3000002 (Aadhaar card), D3000003 (Electricity bill) → Submit → *Account opened*.
2. **Validation:** type a 12-digit Aadhaar → field error "Enter only the last 4 digits…".
3. **Example 4 / 7 (review queue):** `officer1` → Review queue (HIGH risk first) → A2000007 shows the PEP0001 hit
   with similarity and DOB comparison; A2000004 shows 0.7647.
4. **Example 9 → 12 (correction):** open A2000009 → PAN field is amber (0.62) → Correct to `ZZTPS9012Y` with a reason →
   rules re-run → APPROVE → Send to checker. Audit shows before/after.
5. **Example 11 (maker-checker):** `officer_checker` recommends A2000004, then tries to approve it → 403
   "a different checker must decide". `checker1` approves → account number.
6. **Example 10:** `checker1` → Checker queue → A2000010 is a HIGH-risk auto-approval waiting for a checker.
7. **Dashboard / audit / config:** `checker1` → Dashboard; Audit trail (CSV export, PAN masked);
   Config: change `name_match_threshold` to 0.75 → a new example-4 application is auto-approved.

## Layout

```
backend/app/
  main.py, settings.py, db.py, models.py, schemas.py, views.py, auth.py, errors.py, events.py
  services/  rules.py (pure decide R1–R17) · screening.py · dates.py · rules_config.py · datapack.py
             workflow.py (state machine, maker-checker) · extraction.py (provider interface) · audit.py
             reference.py · core_banking.py · masking.py
  routers/   auth · applications · documents · review (officer + checker) · dashboard · audit · config
  cli/       seed.py · batch.py · expire.py
  workers/   notifier.py (Kafka consumer)
backend/tests/   test_rules_sample.py · test_screening_dates.py · test_api.py · test_setup.py
frontend/src/    pages/applicant · pages/officer (queues, workbench) · pages/compliance (dashboard, audit, config)
data/pack/       hackathon data pack (synthetic)
output/          decisions_output.csv (evaluation set) · design/design_document.md
```

## Assumptions (see design doc §20 and §24)

- R1 counts a document as present when the extractor classified it as that type, whatever its confidence;
  low classification confidence is handled by R3 (verified against the expected outputs, e.g. A2000013, A2000047).
- Officer correction re-runs the rules but the case stays IN_REVIEW until the officer recommends; it then goes to the checker.
- On resubmission, a new upload replaces earlier documents of the same declared type.
- `BUSINESS_DATE` sets the application date of new applications (2026-03-04 for the demo data).
- Seeding skips only the "at least 3 uploads" form rule for the data-pack applications that have 2 documents,
  so R1 DOCUMENT_MISSING decides them as in the expected file.
