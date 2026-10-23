"""Mock core-banking service: opens an account for an approved application.
Called only by the backend, authenticated with CORE_BANKING_KEY from the environment."""
import hashlib

from app.errors import ApiError
from app.settings import settings


def open_account(application_id: str, service_key: str) -> tuple[str, str]:
    """Return (customer_id, account_no). Deterministic, so a retry returns the same account."""
    if not settings.core_banking_key or service_key != settings.core_banking_key:
        raise ApiError(503, "CORE_BANKING_UNAVAILABLE", "Core banking service rejected the request")
    digits = int(hashlib.sha256(application_id.encode()).hexdigest(), 16) % 10**10
    return f"CUST{application_id[1:]}", f"5010{digits:010d}"
