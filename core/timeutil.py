"""Timezone helpers so "today" / "tomorrow" mean the company's day, not UTC's."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.app_timezone)
    except Exception:
        return ZoneInfo("UTC")


def now_local() -> datetime:
    return datetime.now(_tz())


def today_local() -> date:
    return now_local().date()


def describe_today() -> str:
    """e.g. 'Wednesday, 2026-10-28' - handed to the LLM so it can resolve
    'by Friday' / 'next Monday' into a concrete ISO date."""
    d = today_local()
    return f"{d.strftime('%A')}, {d.isoformat()}"


def parse_date(value) -> date | None:
    """Accepts ISO strings; returns None for empty input, raises ValueError for junk."""
    if value in (None, "", "null", "none"):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip().lower()
    if text == "today":
        return today_local()
    if text == "tomorrow":
        return today_local() + timedelta(days=1)
    return date.fromisoformat(text[:10])
