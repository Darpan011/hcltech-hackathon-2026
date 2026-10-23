"""Calendar-date helpers (all dates are plain calendar dates in IST)."""
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def parse_date(value) -> date | None:
    """Parse YYYY-MM-DD (or a date object); None if empty or not a valid date."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def age_on(dob: date, on: date) -> int:
    """Completed years on a given date."""
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def add_years(d: date, years: int) -> date:
    """Same day N years later; 29 February becomes 28 February in a non-leap year."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()
