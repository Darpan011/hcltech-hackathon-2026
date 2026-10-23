"""Masking for lists, logs, exports and events (case §6.1.2 data protection)."""


def mask_pan(pan: str | None) -> str:
    """ZZKPS1234Q -> ZZKXXXXX4Q"""
    return f"{pan[:3]}XXXXX{pan[-2:]}" if pan and len(pan) == 10 else (pan or "")


def mask_mobile(mobile: str | None) -> str:
    """9876543210 -> 98XXXXXX10"""
    return f"{mobile[:2]}XXXXXX{mobile[-2:]}" if mobile and len(mobile) == 10 else (mobile or "")


def mask_account(account_no: str | None) -> str:
    return f"XXXXXXXXXX{account_no[-4:]}" if account_no else ""
