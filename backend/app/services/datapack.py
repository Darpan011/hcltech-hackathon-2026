"""Readers for the hackathon data pack (CSV / JSONL / JSON). Used by seed, batch and tests.

Uses the csv module (not pandas) so values like Aadhaar "0037" stay strings.
"""
import csv
import json
from pathlib import Path

from app.services.rules import AppInput, DocInput, Field, ReferenceData
from app.services.dates import parse_date
from app.services.rules_config import RulesConfig
from app.services.screening import WatchlistEntry

FILES = {
    "rules_config": "case_02_rules_config_V1.0.json",
    "occupations": "case_02_occupations_V1.0.csv",
    "sanctions": "case_02_sanctions_list_V1.0.csv",
    "pep": "case_02_pep_list_V1.0.csv",
    "existing_customers": "case_02_existing_customers_V1.0.csv",
    "applications_sample": "case_02_applications_sample_V1.0.csv",
    "documents_sample": "case_02_documents_sample_V1.0.csv",
    "extraction_sample": "case_02_extraction_mock_sample_V1.0.csv",
    "text_sample": "case_02_document_text_sample_V1.0.jsonl",
    "applications_eval": "case_02_applications_eval_V1.0.csv",
    "documents_eval": "case_02_documents_eval_V1.0.csv",
    "extraction_eval": "case_02_extraction_mock_eval_V1.0.csv",
    "text_eval": "case_02_document_text_eval_V1.0.jsonl",
}


def path(data_dir: str | Path, key: str) -> Path:
    return Path(data_dir) / FILES[key]


def read_csv(file: str | Path) -> list[dict]:
    with open(file, newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def read_jsonl(file: str | Path) -> list[dict]:
    with open(file, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def read_config(file: str | Path) -> dict:
    with open(file, encoding="utf-8") as fh:
        return json.load(fh)


def read_extraction(file: str | Path) -> dict[str, list[tuple[str, str, float]]]:
    """Long-format mock file -> {doc_id: [(field_name, value, confidence), ...]}."""
    out: dict[str, list[tuple[str, str, float]]] = {}
    for row in read_csv(file):
        out.setdefault(row["doc_id"], []).append((row["field_name"], row["value"], float(row["confidence"])))
    return out


def doc_input(doc_ref: str, declared_type: str, rows: list[tuple[str, str, float]] | None) -> DocInput:
    """Build a DocInput from long-format rows; no rows = unknown document (OTHER, 0.00)."""
    doc_type, doc_conf, fields = "OTHER", 0.0, {}
    for name, value, conf in rows or []:
        if name == "doc_type":
            doc_type, doc_conf = value, conf
        else:
            fields[name] = Field(value, conf)
    return DocInput(doc_ref, declared_type, doc_type, doc_conf, fields)


def app_input(row: dict) -> AppInput:
    return AppInput(
        application_id=row["application_id"],
        application_date=parse_date(row["application_date"]),
        full_name=row["full_name"],
        dob=row["dob"],
        pan_number=row["pan_number"],
        aadhaar_last4=row["aadhaar_last4"],
        pincode=row["pincode"],
        occupation_code=row["occupation_code"],
        annual_income=float(row["annual_income"] or 0),
    )


def watchlists(sanctions_rows: list[dict], pep_rows: list[dict]) -> tuple[list[WatchlistEntry], list[WatchlistEntry]]:
    sanctions = [WatchlistEntry("SANCTIONS", r["list_id"], r["name"], r.get("alias", ""), r.get("dob", ""),
                                r.get("program", "")) for r in sanctions_rows]
    pep = [WatchlistEntry("PEP", r["pep_id"], r["name"], "", r.get("dob", ""), r.get("position", ""))
           for r in pep_rows]
    return sanctions, pep


def reference_from_files(data_dir: str | Path) -> tuple[RulesConfig, ReferenceData]:
    cfg = RulesConfig.from_dict(read_config(path(data_dir, "rules_config")))
    sanctions, pep = watchlists(read_csv(path(data_dir, "sanctions")), read_csv(path(data_dir, "pep")))
    ref = ReferenceData(
        sanctions=sanctions,
        pep=pep,
        existing_pans={r["pan_number"].upper() for r in read_csv(path(data_dir, "existing_customers"))},
        occupation_risk={r["occupation_code"]: r["risk_level"] for r in read_csv(path(data_dir, "occupations"))},
    )
    return cfg, ref
