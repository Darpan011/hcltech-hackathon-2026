"""Rules configuration (Compliance Officer) and reference lists for the UI."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import COMPLIANCE_OFFICER, CurrentUser, current_user, require_roles
from app.db import get_db
from app.errors import ApiError
from app.models import ConfigEntry, Occupation
from app.schemas import ConfigUpdateIn
from app.services import audit, reference
from app.services.dates import now_ist
from app.services.rules_config import RulesConfig

router = APIRouter(tags=["config"])
_UNIT_INTERVAL_KEYS = {"min_field_confidence", "name_match_threshold", "name_reject_below",
                       "watchlist_match_threshold", "watchlist_possible_threshold"}


@router.get("/config")
def get_config(db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles(COMPLIANCE_OFFICER))) -> list:
    return [{"key": c.key, "value": c.value, "updated_at": c.updated_at}
            for c in db.scalars(select(ConfigEntry).order_by(ConfigEntry.key))]


@router.put("/config/{key}")
def update_config(key: str, body: ConfigUpdateIn, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_roles(COMPLIANCE_OFFICER))) -> dict:
    """Change one threshold; applies to the next rules run with no code change (FR-4)."""
    entry = db.get(ConfigEntry, key)
    if entry is None:
        raise ApiError(404, "NOT_FOUND", f"Unknown config key '{key}'")

    def bad(msg: str):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid config value", [{"field": "value", "message": msg}])

    old, new = entry.value, body.value
    numeric = (int, float)
    if isinstance(old, numeric) and not isinstance(old, bool):
        if isinstance(new, bool) or not isinstance(new, numeric):
            bad("Must be a number")
        if key in _UNIT_INTERVAL_KEYS and not 0 <= new <= 1:
            bad("Must be between 0 and 1")
    elif type(old) is not type(new):
        bad(f"Must be a {type(old).__name__}")
    try:
        RulesConfig.from_dict({**reference.config_dict(db), key: new})
    except (KeyError, TypeError, ValueError, AttributeError):
        bad("Value is not valid for this setting")

    entry.value, entry.updated_at = new, now_ist()
    audit.log(db, action="CONFIG_CHANGED", entity="CONFIG", entity_id=key, actor=(user.id, COMPLIANCE_OFFICER),
              before={"value": old}, after={"value": new})
    db.commit()
    return {"key": key, "value": entry.value, "updated_at": entry.updated_at}


@router.get("/reference/occupations")
def occupations(db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)) -> list:
    return [{"occupation_code": o.occupation_code, "description": o.description}
            for o in db.scalars(select(Occupation).order_by(Occupation.description))]
