"""Batch decisions (FR-11): applications + documents + extraction files -> decisions_output.csv.

Example (sample set, compare with expected columns):
  python -m app.cli.batch --set sample --compare
Example (evaluation set):
  python -m app.cli.batch --set eval
Explicit files:
  python -m app.cli.batch --applications A.csv --documents D.csv --extraction E.csv --out out.csv
"""
import argparse
import csv
import sys
from pathlib import Path

from app.services import datapack
from app.services.rules import decide, format_score
from app.settings import settings

COLUMNS = ["application_id", "decision", "reason_codes", "name_match_score", "risk_category", "rekyc_due_date"]


def run_batch(applications: Path, documents: Path, extraction: Path, data_dir: Path) -> list[dict]:
    """Decide every application in the files; returns output rows in input order."""
    cfg, ref = datapack.reference_from_files(data_dir)
    extracted = datapack.read_extraction(extraction)
    docs_by_app: dict[str, list] = {}
    for row in datapack.read_csv(documents):
        doc = datapack.doc_input(row["doc_id"], row["declared_doc_type"], extracted.get(row["doc_id"]))
        docs_by_app.setdefault(row["application_id"], []).append(doc)

    out = []
    for row in datapack.read_csv(applications):
        d = decide(datapack.app_input(row), docs_by_app.get(row["application_id"], []), cfg, ref)
        out.append({
            "application_id": row["application_id"],
            "decision": d.decision,
            "reason_codes": "|".join(d.reason_codes),
            "name_match_score": format_score(d.name_match_score),
            "risk_category": d.risk_category or "",
            "rekyc_due_date": d.rekyc_due_date.isoformat() if d.rekyc_due_date else "",
        })
    return out


def compare(rows: list[dict], applications: Path) -> list[dict]:
    """Diff against the expected_* columns of a sample applications file."""
    expected = {r["application_id"]: r for r in datapack.read_csv(applications)}
    diffs = []
    for row in rows:
        exp = expected[row["application_id"]]
        for col in COLUMNS[1:]:
            want = exp.get(f"expected_{col}", "")
            if row[col] != want:
                diffs.append({"application_id": row["application_id"], "field": col, "expected": want, "got": row[col]})
    return diffs


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--set", choices=["sample", "eval"], help="use the data-pack files of this set")
    p.add_argument("--data-dir", default=settings.data_dir)
    p.add_argument("--applications")
    p.add_argument("--documents")
    p.add_argument("--extraction")
    p.add_argument("--out", default=None)
    p.add_argument("--compare", action="store_true", help="diff against expected_* columns (sample only)")
    a = p.parse_args()

    data_dir = Path(a.data_dir)
    if a.set:
        applications = datapack.path(data_dir, f"applications_{a.set}")
        documents = datapack.path(data_dir, f"documents_{a.set}")
        extraction = datapack.path(data_dir, f"extraction_{a.set}")
    elif a.applications and a.documents and a.extraction:
        applications, documents, extraction = Path(a.applications), Path(a.documents), Path(a.extraction)
    else:
        p.error("give --set sample|eval, or --applications, --documents and --extraction")
    out = Path(a.out) if a.out else Path(settings.output_dir) / "decisions_output.csv"

    rows = run_batch(applications, documents, extraction, data_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts = {k: sum(1 for r in rows if r["decision"] == k) for k in ("APPROVE", "REVIEW", "REJECT")}
    print(f"Wrote {len(rows)} rows to {out}  {counts}")

    if a.compare:
        diffs = compare(rows, applications)
        if diffs:
            print(f"{len(diffs)} mismatches:")
            for d in diffs:
                print(f"  {d['application_id']:<10} {d['field']:<18} expected={d['expected']!r:<45} got={d['got']!r}")
            return 1
        print(f"All {len(rows)} rows match the expected columns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
