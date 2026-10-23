# OnboardIQ — Manual Test Cases

Logins: `applicant_demo`, `officer1`, `officer2`, `checker1`, `officer_checker` — password `Demo@123`.
Test documents: `data/upload_demo/<doc_id>.txt` (never rename them — the mock reader finds them by file name).

**How to create a test application:** applicant → New application → **Fill demo data** → change only the fields listed → Save → upload the files with the listed types → Submit.
Fill demo data = Ravi Kumar Sharma, DOB 1990-05-15, PAN ZZKPS1234Q, Aadhaar 4821, Flat 12, Lotus Residency, MG Road, Mumbai, pincode 400001, Salaried private, ₹9,00,000.

Abbreviations: EB = Electricity bill, BS = Bank statement, DL = Driving licence.

---

## A. Positive (happy-path) cases

| ID | Scenario | Change fields | Upload (type) | Expected |
|---|---|---|---|---|
| P1 | Clean application, straight-through | none | D3000001 (PAN), D3000002 (Aadhaar), D3000003 (EB) | **Auto-approved**, account number shown, timeline: Submitted → Checking documents → Auto-approved |
| P2 | Name ≥ 0.90 still passes (0.9091, "Aish Gupta" on PAN) | Name `Aisha Gupta`, DOB `1981-09-19`, PAN `ZZPPG8477Z`, Aadhaar `3190`, Address `Flat 368, Lotus Residency, Market Lane, Bengaluru, Karnataka`, City `Bengaluru`, State `Karnataka`, Pincode `560046`, Occupation Business owner, Income `2400000` | D3000031 (PAN), D3000032 (Aadhaar), D3000033 (BS) | **Auto-approved**, risk MEDIUM, re-KYC 2034-03-04 |
| P3 | Title word ignored ("Shri" on PAN) | Name `Varun Chandra Verma`, DOB `1973-02-16`, PAN `ZZXPV0805N`, Aadhaar `3326`, Address `Door No. 188, Lotus Residency, Station Road, Hyderabad, Telangana`, Pincode `500047`, Occupation Professional, Income `4500000` | D3000080 (PAN), D3000081 (Aadhaar), D3000082 (BS) | **Auto-approved**, name match 1.0000, risk MEDIUM (income ≥ ₹25L) |
| P4 | HIGH-risk approval needs a checker (example 10) | Name `Fatima Khan`, Gender F, DOB `1979-04-25`, PAN `ZZUPK0123Z`, Aadhaar `8024`, Occupation Jeweller / bullion dealer, Income `1800000` | D3000028 (PAN), D3000029 (Aadhaar), D3000030 (DL) | **Pending checker**; `checker1` approves → **Approved** + account no. |
| P5 | Officer fixes a misread field (examples 9 → 12) | Name `Imran Shaikh`, DOB `1983-12-12`, PAN `ZZTPS9012Y`, Aadhaar `1357` | D3000025 (PAN), D3000026 (Aadhaar), D3000027 (EB) | **In review** (LOW_EXTRACTION_CONFIDENCE). `officer1` → Correct pan_number → `ZZTPS9012Y` + reason → decision APPROVE → Send to checker → `checker1` approves → **Approved** |
| P6 | Officer recommends approve on a minor name difference (example 4) | DOB `1992-01-20`, PAN `ZZNPS4567T`, Aadhaar `7781` | D3000010 (PAN), D3000011 (Aadhaar), D3000012 (EB) | **In review**, NAME_MISMATCH_MINOR 0.7647 → officer recommends APPROVE → checker approves → **Approved** |
| P7 | Resubmission fixes an old bill | Name `Meera Joshi`, Gender F, DOB `1988-07-07`, PAN `ZZPPJ5678U`, Aadhaar `6612` | D3000013 (PAN), D3000014 (Aadhaar), D3000015 (EB) | **In review** (ADDRESS_PROOF_STALE). Officer → "Ask applicant to resubmit". Applicant sees due date → uploads D3000003 as EB (old bill shown "replaced") → Submit → **Auto-approved** |
| P8 | Checker sends back, officer re-decides | any In-review case after officer recommends | — | Checker → "Send back to officer" → case returns to Review queue; officer recommends again; a different checker decides |
| P9 | Applicant registers a new account | Login page → Create an account | — | Logged in as the new applicant, empty "My applications" |
| P10 | Batch output (FR-11) | `python -m app.cli.batch --set sample --compare` | — | "All 60 rows match the expected columns" |

## B. Rule edge cases (one rule each)

| ID | Rule | Change fields | Upload (type) | Expected |
|---|---|---|---|---|
| R1 | DOCUMENT_MISSING | none | D3000001 (PAN), D3000003 (EB), D3000012 (EB) — no Aadhaar | **In review**, DOCUMENT_MISSING |
| R2 | DOCUMENT_TYPE_MISMATCH (+ missing) | Name `Sneha Reddy`, Gender F, DOB `1995-03-30`, PAN `ZZSPR8901X`, Aadhaar `2468` | D3000022 (PAN), **D3000023 as Aadhaar** (it is a bank statement), D3000024 (BS) | **In review**, DOCUMENT_MISSING \| DOCUMENT_TYPE_MISMATCH |
| R3 | Unknown document | none | your own `test.txt` (PAN), D3000002 (Aadhaar), D3000003 (EB) | **In review**, DOCUMENT_MISSING \| DOCUMENT_TYPE_MISMATCH \| LOW_EXTRACTION_CONFIDENCE (classified OTHER, 0.00) |
| R4 | AGE_BELOW_18 | Name `Kavya Iyer`, Gender F, DOB `2008-09-10`, PAN `ZZLPI2345R`, Aadhaar `1203`, Occupation Student, Income `0` | D3000004 (PAN), D3000005 (Aadhaar), D3000006 (BS) | **Auto-rejected**, AGE_BELOW_18; applicant sees "You must be 18 or older" |
| R5 | PAN_INVALID (4th char not P) | Name `Sanjay Prasad Patel`, DOB `1968-11-22`, PAN `ZZICP3330C`, Aadhaar `5480`, Pincode `380066` | D3000117 (PAN), D3000118 (Aadhaar), D3000119 (BS) | Form accepts it (format OK) → **Auto-rejected**, PAN_INVALID |
| R6 | PAN_MISMATCH (example 3) | Name `Arjun Nair`, DOB `1985-11-02`, PAN `ZZMPN3456S`, Aadhaar `5530` | D3000007 (PAN), D3000008 (Aadhaar), D3000009 (EB) | **Auto-rejected**, PAN_MISMATCH (card shows ZZMPN3465S) |
| R7 | DOB_MISMATCH | DOB `1990-05-16` | D3000001, D3000002, D3000003 | **Auto-rejected**, DOB_MISMATCH |
| R8 | AADHAAR_MISMATCH | Aadhaar `4822` | D3000001, D3000002, D3000003 | **Auto-rejected**, AADHAAR_MISMATCH |
| R9 | NAME_MISMATCH (< 0.75) | Name `Rahul Verma` | D3000001, D3000002, D3000003 | **Auto-rejected**, NAME_MISMATCH |
| R10 | SANCTIONS_MATCH (example 6) | Name `Valko Quillon`, DOB `1986-02-23`, PAN `ZZQPV6789V`, Aadhaar `3390` | D3000016 (PAN), D3000017 (Aadhaar), D3000018 (BS) | **Auto-rejected**; applicant sees only "Additional verification is required" |
| R11 | NAME_MISMATCH_MINOR | see P6 | | **In review**, score 0.7647 |
| R13 | ADDRESS_PROOF_STALE | see P7 | | **In review** (bill 120 days old) |
| R14 | ADDRESS_MISMATCH | Name `Tanvi Das`, Gender F, DOB `1990-01-31`, PAN `ZZQPD1766S`, Aadhaar `5774`, Pincode `302034`, Occupation Self-employed | D3000101 (PAN), D3000102 (Aadhaar), D3000103 (EB) | **In review**, ADDRESS_MISMATCH (bill pincode 302041) |
| R16 | PEP_MATCH (example 7) | Name `Zoya Menon`, Gender F, DOB `1982-10-15`, PAN `ZZRPM7890W`, Aadhaar `9045` | D3000019 (PAN), D3000020 (Aadhaar), D3000021 (BS) | **In review**, risk HIGH, re-KYC 2028-03-04; officer sees PEP0001, similarity 1.0000, DOB SAME |
| R-low | Low confidence on Aadhaar only | Name `Zoya Verma`, Gender F, DOB `1977-11-26`, PAN `ZZEPV0742D`, Aadhaar `0478`, Address `Flat 195, Ganga Enclave, Hill Road, Delhi, Delhi`, Pincode `110041` | D3000077 (PAN), D3000078 (Aadhaar), D3000079 (BS) | **In review**, LOW_EXTRACTION_CONFIDENCE only — misread DOB/Aadhaar are **not** used to reject (amber rows) |

Rules with no UI data in the sample pack: R12 DOCUMENT_EXPIRED, R15 SANCTIONS_POSSIBLE_MATCH, R17 DUPLICATE_CUSTOMER — covered by automated tests; to see R12/R15 in the UI, load the evaluation set: `python -m app.cli.seed --with-eval-apps` (e.g. A2100007, A2100037, A2100087 = possible sanctions match).

## C. Form validation edge cases (should show a red field error, nothing saved)

| ID | Input | Expected message |
|---|---|---|
| V1 | Aadhaar `123456784821` (12 digits) | "Enter only the last 4 digits of Aadhaar, not the full 12-digit number" |
| V2 | Aadhaar `48a1` or `482` | "Enter the last 4 digits of your Aadhaar" |
| V3 | PAN `ZZK1234Q` / `12345ABCDE` | "PAN must look like ABCDE1234F" |
| V4 | PAN `zzkps1234q` (lower case) | **Accepted**, stored upper case |
| V5 | Mobile `5876500000` or 9 digits | "Mobile must be a 10-digit Indian number" |
| V6 | Pincode `040001` or `40001` | "Pincode must be 6 digits and not start with 0" |
| V7 | DOB in the future | "Date of birth cannot be in the future" |
| V8 | Consent unticked | "Consent to KYC checks is required" |
| V9 | Occupation not selected | error on occupation_code |
| V10 | Income `-5` / empty | error on annual_income |
| V11 | Email `ravi@` | "Enter a valid email address" |
| V12 | Name `R` (1 char) | error on full_name |

## D. Upload edge cases

| ID | Action | Expected |
|---|---|---|
| U1 | Upload a `.pdf` / `.jpg` / `.docx` | "Only UTF-8 .txt files up to 1 MB are allowed" |
| U2 | Upload an empty `.txt` (0 bytes) | same error |
| U3 | Upload a `.txt` larger than 1 MB | same error |
| U4 | Upload the same file twice | "This file was already uploaded." — listed once |
| U5 | Only 2 files uploaded | Submit disabled, "Upload at least 3 documents to submit" |
| U6 | Two bills (D3000003 + D3000012) | Accepted; rules use the lowest doc id as address proof |
| U7 | After submit | Upload box disappears (API returns 409 if forced) |
| U8 | Wrong type chosen in dropdown | Accepted at upload; rules flag DOCUMENT_TYPE_MISMATCH (see R2) |

## E. Officer / checker workflow edge cases

| ID | Action | Expected |
|---|---|---|
| W1 | `officer_checker` recommends A2000004, then tries to approve it in Checker queue | Red: "You recommended this case; a different checker must decide" (403) |
| W2 | Comment shorter than 10 characters | "Comment must be at least 10 characters" |
| W3 | Correction reason shorter than 10 characters | same error, nothing changed |
| W4 | Correct pan_number to `ABC` | "PAN must look like ABCDE1234F" |
| W5 | Correct dob to `2026-13-40` | "Use a valid date in YYYY-MM-DD format" |
| W6 | Two officers on the same case: open A2000017 as `officer1` in a normal window and as `officer2` in an **InPrivate/Incognito** window; both recommend | First succeeds; second gets "This case was changed by someone else. Reload it and try again." (409) |
| W7 | Correct a field, then look at the field | Shows new value, conf 1.00, source OFFICER, "was <old value>", reason and officer name |
| W8 | Correction makes decision APPROVE | Status stays **In review** until the officer recommends (maker-checker still applies) |
| W9 | Open a document tab, then check Audit trail as checker | DOCUMENT_VIEWED row with officer id and time |
| W10 | Checker opens a case that is not Pending checker | "No action available in status …" |
| W11 | Review queue order | HIGH risk cases first, then oldest submitted |

## F. Security / access

| ID | Action | Expected |
|---|---|---|
| S1 | Applicant opens `/review` or `/dashboard` | "Your role cannot open this page." (API returns 403) |
| S2 | New registered applicant opens `/my/A2000001` | Not found (404) — cannot see another person's application |
| S3 | Wrong password | "Wrong username or password" |
| S4 | Call API without login: http://127.0.0.1:8000/docs → try `GET /applications/mine` | 401 "Please log in" |
| S5 | Officer opens `/audit/A2000001` URL | Role message (audit is Compliance only) |
| S6 | Applicant view of a rejected/reviewed case | Plain-language reasons only — no confidence scores, no watchlist entry names |
| S7 | Lists and audit export | PAN masked as `ZZKXXXXX4Q`; full Aadhaar never stored |

## G. Compliance features

| ID | Action | Expected |
|---|---|---|
| C1 | Dashboard | Tiles + chart; total = sum of statuses; date filter changes numbers |
| C2 | Config: set `name_match_threshold` to `7` | "Must be between 0 and 1" |
| C3 | Config: set `name_match_threshold` to `0.75`, then redo P6 as a new application | **Auto-approved** (no code change). Set it back to `0.9` afterwards |
| C4 | Audit trail of A2000009 after P5 → Export CSV | FIELD_CORRECTED with before/after, PANs masked in the file |
| C5 | Checker queue | A2000010 shows "High-risk auto-approval"; waiting hours; SLA flag after 24 h |

## H. Automated checks (run before the demo)

```powershell
cd backend
pytest -q --ignore=tests/test_setup.py      # without the Kafka client installed
python -m app.cli.batch --set sample --compare
python -m app.cli.batch --set eval           # writes output/decisions_output.csv
```

Reset all demo data any time: `python -m app.cli.seed --reset --with-sample-apps`
