"""Rules engine R1–R17, risk category and re-KYC date (case §6.1, design §8).

PURE function: no database, no HTTP, no clock. The API and the batch CLI both call
`decide()`, so a decision is identical whichever path produced it.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.services.dates import add_years, age_on, parse_date
from app.services.rules_config import RulesConfig
from app.services.screening import ScreeningHit, WatchlistEntry, normalise, screen, similarity

PAN, AADHAAR, ADDRESS = "PAN_CARD", "AADHAAR_CARD", "ADDRESS_PROOF"
DOC_TYPES = ("PAN_CARD", "AADHAAR_CARD", "ELECTRICITY_BILL", "BANK_STATEMENT", "DRIVING_LICENCE")
REQUIRED_FIELDS = {
    "PAN_CARD": ("name", "dob", "pan_number"),
    "AADHAAR_CARD": ("name", "dob", "aadhaar_last4"),
    "ELECTRICITY_BILL": ("pincode", "document_date"),
    "BANK_STATEMENT": ("pincode", "document_date"),
    "DRIVING_LICENCE": ("pincode", "valid_until"),
}
RULES = {  # rule -> (reason code, outcome when triggered)
    "R1": ("DOCUMENT_MISSING", "REVIEW"),
    "R2": ("DOCUMENT_TYPE_MISMATCH", "REVIEW"),
    "R3": ("LOW_EXTRACTION_CONFIDENCE", "REVIEW"),
    "R4": ("AGE_BELOW_18", "REJECT"),
    "R5": ("PAN_INVALID", "REJECT"),
    "R6": ("PAN_MISMATCH", "REJECT"),
    "R7": ("DOB_MISMATCH", "REJECT"),
    "R8": ("AADHAAR_MISMATCH", "REJECT"),
    "R9": ("NAME_MISMATCH", "REJECT"),
    "R10": ("SANCTIONS_MATCH", "REJECT"),
    "R11": ("NAME_MISMATCH_MINOR", "REVIEW"),
    "R12": ("DOCUMENT_EXPIRED", "REVIEW"),
    "R13": ("ADDRESS_PROOF_STALE", "REVIEW"),
    "R14": ("ADDRESS_MISMATCH", "REVIEW"),
    "R15": ("SANCTIONS_POSSIBLE_MATCH", "REVIEW"),
    "R16": ("PEP_MATCH", "REVIEW"),
    "R17": ("DUPLICATE_CUSTOMER", "REVIEW"),
}


@dataclass
class AppInput:
    application_id: str
    application_date: date
    full_name: str
    dob: str                  # declared, YYYY-MM-DD
    pan_number: str
    aadhaar_last4: str
    pincode: str
    occupation_code: str
    annual_income: float


@dataclass
class Field:
    value: str
    confidence: float


@dataclass
class DocInput:
    doc_ref: str
    declared_doc_type: str
    doc_type: str
    doc_type_confidence: float
    fields: dict[str, Field] = field(default_factory=dict)


@dataclass
class ReferenceData:
    sanctions: list[WatchlistEntry]
    pep: list[WatchlistEntry]
    existing_pans: set[str]
    occupation_risk: dict[str, str]


@dataclass
class Decision:
    decision: str
    reason_codes: list[str]
    name_match_score: float | None
    risk_category: str | None
    rekyc_due_date: date | None
    rule_details: list[dict]
    hits: list[ScreeningHit]
    selected: dict[str, str]  # slot -> doc_ref


def format_score(score: float | None) -> str:
    """4 decimals, half-up, for output only (comparisons use the unrounded value)."""
    if score is None:
        return ""
    return str(Decimal(str(score)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def same_date(a: str, b: str) -> bool:
    pa, pb = parse_date(a), parse_date(b)
    return pa == pb if pa and pb else a.strip() == b.strip()


class _Recorder:
    def __init__(self):
        self.details: list[dict] = []

    def add(self, rule: str, triggered: bool, compared: dict, skipped: bool = False) -> None:
        code, outcome = RULES[rule]
        self.details.append({"rule": rule, "code": code, "outcome": outcome,
                             "triggered": bool(triggered) and not skipped,
                             "skipped": skipped, "compared": compared})

    def triggered(self) -> list[dict]:
        return [d for d in self.details if d["triggered"]]


def decide(app: AppInput, docs: list[DocInput], cfg: RulesConfig, ref: ReferenceData) -> Decision:
    """Evaluate R1–R17 for one application and return the decision with full explanation."""
    min_conf = cfg.min_field_confidence
    titles = set(cfg.name_title_tokens)
    ordered = sorted(docs, key=lambda d: d.doc_ref)

    def first(types: set[str]) -> DocInput | None:
        return next((d for d in ordered if d.doc_type in types), None)

    pan_doc, aad_doc, addr_doc = first({PAN}), first({AADHAAR}), first(set(cfg.address_proof_types))
    selected = {slot: d for slot, d in ((PAN, pan_doc), (AADHAAR, aad_doc), (ADDRESS, addr_doc)) if d}

    def usable(doc: DocInput | None, name: str) -> str | None:
        f = doc.fields.get(name) if doc else None
        if f is None or not str(f.value).strip() or f.confidence < min_conf:
            return None
        return str(f.value).strip()

    r = _Recorder()
    declared_pan = (app.pan_number or "").strip().upper()
    declared_dob = parse_date(app.dob)
    declared_dob_str = declared_dob.isoformat() if declared_dob else (app.dob or "").strip()

    # R1 — a PAN card, an Aadhaar card and one address proof must be present (by classified type)
    missing = [slot for slot in (PAN, AADHAAR, ADDRESS) if slot not in selected]
    r.add("R1", bool(missing), {"missing": missing})

    # R2 — classified type differs from what the customer declared
    mismatched = [{"doc": d.doc_ref, "declared": d.declared_doc_type, "classified": d.doc_type}
                  for d in ordered if d.doc_type != d.declared_doc_type]
    r.add("R2", bool(mismatched), {"documents": mismatched})

    # R3 — low classification confidence on any doc, or a required field of a selected doc unusable
    low = [{"doc": d.doc_ref, "field": "doc_type", "confidence": d.doc_type_confidence}
           for d in ordered if d.doc_type_confidence < min_conf]
    for d in selected.values():
        for name in REQUIRED_FIELDS.get(d.doc_type, ()):
            if usable(d, name) is None:
                f = d.fields.get(name)
                low.append({"doc": d.doc_ref, "field": name, "confidence": f.confidence if f else None})
    r.add("R3", bool(low), {"min_confidence": min_conf, "fields": low})

    # R4 — age on application date
    if declared_dob:
        age = age_on(declared_dob, app.application_date)
        r.add("R4", age < cfg.min_age, {"age": age, "min_age": cfg.min_age})
    else:
        r.add("R4", False, {"reason": "declared dob invalid"}, skipped=True)

    # R5 — PAN format and individual holder type (4th character)
    pan_ok = bool(re.fullmatch(cfg.pan_pattern, declared_pan)) and declared_pan[3:4] == cfg.pan_holder_type_char
    r.add("R5", not pan_ok, {"declared": declared_pan, "fourth_char": declared_pan[3:4],
                             "required": cfg.pan_holder_type_char})

    # R6 — PAN on the card vs declared PAN
    card_pan = usable(pan_doc, "pan_number")
    if card_pan is None:
        r.add("R6", False, {"reason": "PAN number on card not usable"}, skipped=True)
    else:
        r.add("R6", card_pan.upper() != declared_pan, {"declared": declared_pan, "extracted": card_pan.upper()})

    # R7 — DOB on PAN and/or Aadhaar vs declared DOB
    dob_checks = {slot: usable(d, "dob") for slot, d in ((PAN, pan_doc), (AADHAAR, aad_doc))}
    dob_checks = {slot: v for slot, v in dob_checks.items() if v is not None}
    if not dob_checks:
        r.add("R7", False, {"reason": "no usable dob on PAN or Aadhaar"}, skipped=True)
    else:
        bad = [slot for slot, v in dob_checks.items() if not same_date(v, declared_dob_str)]
        r.add("R7", bool(bad), {"declared": declared_dob_str, "extracted": dob_checks, "mismatch_on": bad})

    # R8 — Aadhaar last 4 digits
    card_aadhaar = usable(aad_doc, "aadhaar_last4")
    if card_aadhaar is None:
        r.add("R8", False, {"reason": "Aadhaar digits on card not usable"}, skipped=True)
    else:
        declared_aadhaar = (app.aadhaar_last4 or "").strip()
        r.add("R8", card_aadhaar != declared_aadhaar, {"declared": declared_aadhaar, "extracted": card_aadhaar})

    # Name match score = lowest similarity vs usable names on PAN and Aadhaar
    declared_norm = normalise(app.full_name, titles)
    name_scores: dict[str, dict] = {}
    for slot, d in ((PAN, pan_doc), (AADHAAR, aad_doc)):
        v = usable(d, "name")
        if v is not None:
            norm = normalise(v, titles)
            name_scores[slot] = {"name": norm, "similarity": similarity(declared_norm, norm)}
    score = min(s["similarity"] for s in name_scores.values()) if name_scores else None
    name_compared = {"declared": declared_norm, "documents": name_scores, "score": score}

    # Watchlists (declared name + declared dob)
    s_result, s_hit = screen(app.full_name, declared_dob_str, ref.sanctions, titles,
                             cfg.watchlist_match_threshold, cfg.watchlist_possible_threshold)
    p_result, p_hit = screen(app.full_name, declared_dob_str, ref.pep, titles,
                             cfg.watchlist_match_threshold, cfg.watchlist_possible_threshold)

    # R9 — name clearly different
    if score is None:
        r.add("R9", False, {"reason": "no usable name on PAN or Aadhaar"}, skipped=True)
    else:
        r.add("R9", score < cfg.name_reject_below, {**name_compared, "reject_below": cfg.name_reject_below})

    # R10 — sanctions MATCH
    r.add("R10", s_result == "MATCH", {"result": s_result, "hit": s_hit.as_dict() if s_hit else None})

    # R11 — name slightly different
    if score is None:
        r.add("R11", False, {"reason": "no usable name on PAN or Aadhaar"}, skipped=True)
    else:
        r.add("R11", cfg.name_reject_below <= score < cfg.name_match_threshold,
              {**name_compared, "pass_at": cfg.name_match_threshold})

    # R12 / R13 / R14 — address proof checks
    addr_type = addr_doc.doc_type if addr_doc else None
    valid_until = parse_date(usable(addr_doc, "valid_until")) if addr_type == "DRIVING_LICENCE" else None
    if valid_until is None:
        r.add("R12", False, {"reason": "no usable driving licence validity"}, skipped=True)
    else:
        r.add("R12", valid_until < app.application_date,
              {"valid_until": valid_until.isoformat(), "application_date": app.application_date.isoformat()})

    doc_date = (parse_date(usable(addr_doc, "document_date"))
                if addr_type in ("ELECTRICITY_BILL", "BANK_STATEMENT") else None)
    if doc_date is None:
        r.add("R13", False, {"reason": "no usable bill/statement date"}, skipped=True)
    else:
        age_days = (app.application_date - doc_date).days
        r.add("R13", age_days > cfg.address_proof_max_age_days or doc_date > app.application_date,
              {"document_date": doc_date.isoformat(), "age_days": age_days,
               "max_age_days": cfg.address_proof_max_age_days})

    card_pin = usable(addr_doc, "pincode")
    if card_pin is None:
        r.add("R14", False, {"reason": "no usable pincode on address proof"}, skipped=True)
    else:
        r.add("R14", card_pin != (app.pincode or "").strip(), {"declared": app.pincode, "extracted": card_pin})

    # R15 / R16 / R17
    r.add("R15", s_result == "POSSIBLE", {"result": s_result, "hit": s_hit.as_dict() if s_hit else None})
    r.add("R16", p_result == "MATCH", {"result": p_result, "hit": p_hit.as_dict() if p_hit else None})
    r.add("R17", declared_pan in ref.existing_pans, {"declared": declared_pan})

    # Decision: REJECT > REVIEW > APPROVE; codes in rule order R1..R17
    fired = sorted(r.triggered(), key=lambda d: int(d["rule"][1:]))
    codes = [d["code"] for d in fired]
    if any(d["outcome"] == "REJECT" for d in fired):
        decision = "REJECT"
    elif fired:
        decision = "REVIEW"
    else:
        decision = "APPROVE"

    risk = rekyc = None
    if decision != "REJECT":
        occ_risk = ref.occupation_risk.get(app.occupation_code, "LOW")
        if "PEP_MATCH" in codes or "SANCTIONS_POSSIBLE_MATCH" in codes or occ_risk == "HIGH":
            risk = "HIGH"
        elif occ_risk == "MEDIUM" or float(app.annual_income or 0) >= cfg.medium_risk_income:
            risk = "MEDIUM"
        else:
            risk = "LOW"
        rekyc = add_years(app.application_date, cfg.rekyc_years[risk])

    hits = [h for h in (s_hit, p_hit) if h is not None]
    return Decision(decision, codes, score, risk, rekyc, r.details, hits,
                    {slot: d.doc_ref for slot, d in selected.items()})


def route(decision: Decision) -> str:
    """Decision + risk -> next status (design §8.9)."""
    if decision.decision == "REJECT":
        return "AUTO_REJECTED"
    if decision.decision == "REVIEW":
        return "IN_REVIEW"
    return "PENDING_CHECKER" if decision.risk_category == "HIGH" else "AUTO_APPROVED"
