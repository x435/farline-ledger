"""UTC timestamps for the save envelope. Simulation code does not call this."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware.")
    text = moment.astimezone(timezone.utc).isoformat()
    if not text.endswith("+00:00"):
        raise ValueError("Could not normalize timestamp to UTC.")
    return text[:-6] + "Z"


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Timestamp must be an explicit UTC value ending in Z.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Timestamp is not a valid UTC datetime.") from error
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return parsed.astimezone(timezone.utc)
