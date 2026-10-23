"""Typed view of the rules configuration.

The config keys are exactly the keys of case_02_rules_config_V1.0.json, so the file
loads straight into the `config` table and changing a row changes behaviour (FR-4).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RulesConfig:
    min_field_confidence: float
    min_age: int
    pan_pattern: str
    pan_holder_type_char: str
    name_match_threshold: float          # pass at or above (R11 upper bound)
    name_reject_below: float             # R9 below this, R11 from here
    watchlist_match_threshold: float
    watchlist_possible_threshold: float
    address_proof_max_age_days: int
    medium_risk_income: float
    rekyc_years: dict
    name_title_tokens: frozenset
    address_proof_types: tuple
    resubmission_sla_days: int
    checker_sla_hours: int

    @classmethod
    def from_dict(cls, d: dict) -> "RulesConfig":
        return cls(
            min_field_confidence=float(d["min_field_confidence"]),
            min_age=int(d["min_age"]),
            pan_pattern=str(d["pan_pattern"]),
            pan_holder_type_char=str(d["pan_holder_type_char"]),
            name_match_threshold=float(d["name_match_threshold"]),
            name_reject_below=float(d["name_reject_below"]),
            watchlist_match_threshold=float(d["watchlist_match_threshold"]),
            watchlist_possible_threshold=float(d["watchlist_possible_threshold"]),
            address_proof_max_age_days=int(d["address_proof_max_age_days"]),
            medium_risk_income=float(d["medium_risk_income"]),
            rekyc_years={k: int(v) for k, v in d["rekyc_years"].items()},
            name_title_tokens=frozenset(t.upper() for t in d["name_title_tokens"]),
            address_proof_types=tuple(d["address_proof_types"]),
            resubmission_sla_days=int(d.get("resubmission_sla_days", 7)),
            checker_sla_hours=int(d.get("checker_sla_hours", 24)),
        )
