"""Loads rules config and reference data from the database for each rules run."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConfigEntry, ExistingCustomer, Occupation, PepEntry, SanctionsEntry
from app.services.rules import ReferenceData
from app.services.rules_config import RulesConfig
from app.services.screening import WatchlistEntry


def config_dict(db: Session) -> dict:
    return {c.key: c.value for c in db.scalars(select(ConfigEntry))}


def load(db: Session) -> tuple[RulesConfig, ReferenceData]:
    """Read once per rules run, so a config or watchlist change applies to the next run."""
    cfg = RulesConfig.from_dict(config_dict(db))
    ref = ReferenceData(
        sanctions=[WatchlistEntry("SANCTIONS", s.list_id, s.name, s.alias, s.dob, s.program)
                   for s in db.scalars(select(SanctionsEntry))],
        pep=[WatchlistEntry("PEP", p.pep_id, p.name, "", p.dob, p.position) for p in db.scalars(select(PepEntry))],
        existing_pans={c.upper() for c in db.scalars(select(ExistingCustomer.pan_number))},
        occupation_risk={o.occupation_code: o.risk_level for o in db.scalars(select(Occupation))},
    )
    return cfg, ref
