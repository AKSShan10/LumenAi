"""Small date and time helpers. All times are stored and compared in UTC."""
from datetime import datetime, timezone


# Returns the current time in UTC (used for approved_at and opened_at)
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Some databases give back dates without a time zone; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
