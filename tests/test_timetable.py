from datetime import UTC, date, datetime, time

from app.models import CourseSchedule
from app.services.timetable import earliest, next_slot_start

KTM = "Asia/Kathmandu"  # UTC+05:45, no daylight saving
NY = "America/New_York"  # daylight saving ends Sunday 1 Nov 2026

# Wednesday 18 Nov 2026, 06:00 UTC = 11:45 in Kathmandu.
NOW = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)
COURSE_DATES = (date(2026, 9, 1), date(2026, 12, 31))


def slot(day: int, hh: int, mm: int = 0, tz: str = KTM) -> CourseSchedule:
    return CourseSchedule(day_of_week=day, start_time=time(hh, mm), duration_minutes=60, timezone=tz)


def test_later_today():
    # Wednesday 12:00 Kathmandu is 15 minutes away.
    assert next_slot_start([slot(2, 12)], *COURSE_DATES, NOW) == datetime(2026, 11, 18, 6, 15, tzinfo=UTC)


def test_already_started_today_means_next_week():
    # Wednesday 10:00 Kathmandu started at 04:15 UTC today; next one is a week later.
    assert next_slot_start([slot(2, 10)], *COURSE_DATES, NOW) == datetime(2026, 11, 25, 4, 15, tzinfo=UTC)


def test_earliest_of_several_slots():
    slots = [slot(4, 9), slot(0, 10)]  # Friday 09:00, Monday 10:00
    assert next_slot_start(slots, *COURSE_DATES, NOW) == datetime(2026, 11, 20, 3, 15, tzinfo=UTC)


def test_course_not_started_yet():
    # Starts Tuesday 1 Dec; the first Monday on or after that is 7 Dec.
    result = next_slot_start([slot(0, 10)], date(2026, 12, 1), date(2027, 3, 1), NOW)
    assert result == datetime(2026, 12, 7, 4, 15, tzinfo=UTC)


def test_course_ended():
    assert next_slot_start([slot(0, 10)], date(2026, 9, 1), date(2026, 11, 17), NOW) is None


def test_next_slot_falls_after_last_day():
    # Ends Friday 20 Nov; the next Monday (23 Nov) is past the end.
    assert next_slot_start([slot(0, 10)], date(2026, 9, 1), date(2026, 11, 20), NOW) is None


def test_no_slots():
    assert next_slot_start([], *COURSE_DATES, NOW) is None


def test_wall_clock_time_survives_daylight_saving_change():
    # Monday 09:00 in New York: 13:00 UTC in October, 14:00 UTC after DST ends on 1 Nov.
    tuesday_27_oct = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    result = next_slot_start([slot(0, 9, tz=NY)], *COURSE_DATES, tuesday_27_oct)
    assert result == datetime(2026, 11, 2, 14, 0, tzinfo=UTC)


def test_earliest():
    a = datetime(2026, 1, 1, tzinfo=UTC)
    b = datetime(2026, 1, 2, tzinfo=UTC)
    assert earliest(b, None, a) == a
    assert earliest(None, None) is None
