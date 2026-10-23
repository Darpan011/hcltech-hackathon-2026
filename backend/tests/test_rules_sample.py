"""The main correctness gate: all 60 sample applications must match the expected columns."""
from dataclasses import replace

import pytest

from app.cli.batch import compare, run_batch
from app.services import datapack
from app.services.rules import Field, decide, format_score
from app.services.rules_config import RulesConfig
from app.settings import settings

DATA = settings.data_dir
APPS = datapack.path(DATA, "applications_sample")
DOCS = datapack.path(DATA, "documents_sample")
EXTR = datapack.path(DATA, "extraction_sample")


@pytest.fixture(scope="module")
def case():
    cfg, ref = datapack.reference_from_files(DATA)
    extracted = datapack.read_extraction(EXTR)
    apps = {r["application_id"]: r for r in datapack.read_csv(APPS)}
    docs: dict[str, list] = {}
    for row in datapack.read_csv(DOCS):
        docs.setdefault(row["application_id"], []).append(
            datapack.doc_input(row["doc_id"], row["declared_doc_type"], extracted.get(row["doc_id"])))
    return cfg, ref, apps, docs


def run(case, app_id, cfg=None):
    base_cfg, ref, apps, docs = case
    return decide(datapack.app_input(apps[app_id]), docs[app_id], cfg or base_cfg, ref)


def test_all_60_sample_rows_match_expected():
    rows = run_batch(APPS, DOCS, EXTR, DATA)
    assert len(rows) == 60
    assert compare(rows, APPS) == []


@pytest.mark.parametrize("app_id,decision,codes,score,risk,rekyc", [
    ("A2000001", "APPROVE", [], "1.0000", "LOW", "2036-03-04"),
    ("A2000002", "REJECT", ["AGE_BELOW_18"], "1.0000", None, None),
    ("A2000003", "REJECT", ["PAN_MISMATCH"], "1.0000", None, None),
    ("A2000004", "REVIEW", ["NAME_MISMATCH_MINOR"], "0.7647", "LOW", "2036-03-04"),
    ("A2000005", "REVIEW", ["ADDRESS_PROOF_STALE"], "1.0000", "LOW", "2036-03-04"),
    ("A2000006", "REJECT", ["SANCTIONS_MATCH"], "1.0000", None, None),
    ("A2000007", "REVIEW", ["PEP_MATCH"], "1.0000", "HIGH", "2028-03-04"),
    ("A2000008", "REVIEW", ["DOCUMENT_MISSING", "DOCUMENT_TYPE_MISMATCH"], "1.0000", "LOW", "2036-03-04"),
    ("A2000009", "REVIEW", ["LOW_EXTRACTION_CONFIDENCE"], "1.0000", "LOW", "2036-03-04"),
    ("A2000010", "APPROVE", [], "1.0000", "HIGH", "2028-03-04"),
])
def test_worked_examples(case, app_id, decision, codes, score, risk, rekyc):
    d = run(case, app_id)
    assert d.decision == decision
    assert d.reason_codes == codes
    assert format_score(d.name_match_score) == score
    assert d.risk_category == risk
    assert (d.rekyc_due_date.isoformat() if d.rekyc_due_date else None) == rekyc


def test_watchlist_hits_name_the_entries(case):
    assert [h.entry_id for h in run(case, "A2000006").hits if h.result == "MATCH"] == ["SAN0002"]
    assert [h.entry_id for h in run(case, "A2000007").hits if h.result == "MATCH"] == ["PEP0001"]


def test_example_9_pan_mismatch_not_evaluated_then_officer_fix_approves(case):
    d = run(case, "A2000009")
    r6 = next(x for x in d.rule_details if x["rule"] == "R6")
    assert r6["skipped"] and not r6["triggered"]

    cfg, ref, apps, docs = case
    fixed = [replace(doc, fields={**doc.fields, "pan_number": Field("ZZTPS9012Y", 1.0)})
             if doc.doc_ref == "D3000025" else doc for doc in docs["A2000009"]]
    d2 = decide(datapack.app_input(apps["A2000009"]), fixed, cfg, ref)
    assert d2.decision == "APPROVE" and d2.reason_codes == []


def test_config_change_flips_example_4(case):
    cfg = case[0]
    lenient = replace(cfg, name_match_threshold=0.75)
    assert run(case, "A2000004", lenient).decision == "APPROVE"


def test_duplicate_customer_rule(case):
    cfg, ref, apps, docs = case
    ref_with_dup = replace(ref, existing_pans=ref.existing_pans | {"ZZKPS1234Q"})
    d = decide(datapack.app_input(apps["A2000001"]), docs["A2000001"], cfg, ref_with_dup)
    assert d.decision == "REVIEW" and d.reason_codes == ["DUPLICATE_CUSTOMER"]


def test_unknown_document_is_other_with_zero_confidence():
    doc = datapack.doc_input("D9999999", "PAN_CARD", None)
    assert (doc.doc_type, doc.doc_type_confidence) == ("OTHER", 0.0)


def test_rules_config_loads_from_json():
    cfg = RulesConfig.from_dict(datapack.read_config(datapack.path(DATA, "rules_config")))
    assert cfg.name_match_threshold == 0.9 and "KUMARI" in cfg.name_title_tokens
