from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import CourseSchedule


def next_slot_start(
    schedules: Iterable[CourseSchedule], starts_on: date, ends_on: date, now: datetime
) -> datetime | None:
    """Start (in UTC) of the next weekly slot after `now`, within the course's dates.

    Each slot is a wall-clock time in its own timezone, so the next date is found
    in that timezone first and only then converted to UTC. That keeps a 10:00
    class at 10:00 local time when daylight saving time changes.
    """
    best: datetime | None = None
    for slot in schedules:
        tz = ZoneInfo(slot.timezone)
        local_now = now.astimezone(tz)
        day = max(local_now.date(), starts_on)
        day += timedelta(days=(slot.day_of_week - day.weekday()) % 7)
        start = datetime.combine(day, slot.start_time, tzinfo=tz)
        if start <= local_now:  # today's slot has already started
            start = datetime.combine(day + timedelta(days=7), slot.start_time, tzinfo=tz)
        if start.date() > ends_on:
            continue
        start_utc = start.astimezone(UTC)
        if best is None or start_utc < best:
            best = start_utc
    return best


def earliest(*times: datetime | None) -> datetime | None:
    known = [t for t in times if t is not None]
    return min(known) if known else None
