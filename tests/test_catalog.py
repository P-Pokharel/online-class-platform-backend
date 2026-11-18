from datetime import UTC, datetime, time, timedelta

import pytest

from app.core.deps import ACCESS_TOKEN_COOKIE
from app.models import Enrollment, EnrollmentStatus, SessionStatus, UserRole
from app.schemas.courses import short_description
from tests.conftest import login_as

COURSES = "/api/v1/courses"
MONDAY_10_KTM = (0, time(10, 0), "Asia/Kathmandu")


@pytest.fixture
def teacher(make_teacher):
    return make_teacher(title="Professor")


def enroll_row(db, student, course, status=EnrollmentStatus.ACTIVE):
    db.add(Enrollment(student=student, course=course, status=status))
    db.commit()


# --- list ------------------------------------------------------------------------


def test_anonymous_sees_only_published(client, teacher, make_course):
    make_course(teacher, code="CS101", schedules=[MONDAY_10_KTM], price_cents=4999)
    make_course(teacher, code="DRAFT1", is_published=False)

    res = client.get(COURSES)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    card = body["items"][0]
    assert card["code"] == "CS101"
    assert card["price_cents"] == 4999
    assert card["teacher"] == {"id": teacher.id, "full_name": teacher.user.full_name,
                               "title": "Professor"}
    assert card["schedules"][0]["timezone"] == "Asia/Kathmandu"
    assert card["is_enrolled"] is None
    assert card["is_live"] is False
    assert card["enrolled_count"] == 0


def test_search_teacher_filter_and_pagination(client, make_teacher, make_course):
    t1, t2 = make_teacher(), make_teacher()
    make_course(t1, code="CS101", title="Intro to Programming")
    make_course(t1, code="CS201", title="Data Structures")
    make_course(t2, code="MATH201", title="Linear Algebra")

    def codes(**params):
        return [c["code"] for c in client.get(COURSES, params=params).json()["items"]]

    assert codes() == ["CS101", "CS201", "MATH201"]
    assert codes(search="algebra") == ["MATH201"]
    assert codes(search="cs2") == ["CS201"]
    assert codes(teacher_id=t1.id) == ["CS101", "CS201"]
    page2 = client.get(COURSES, params={"page": 2, "page_size": 2}).json()
    assert [c["code"] for c in page2["items"]] == ["MATH201"] and page2["total"] == 3


def test_enrolled_count_and_live_status(client, teacher, make_course, make_user, make_session, db):
    course = make_course(teacher)
    enroll_row(db, make_user(), course)
    enroll_row(db, make_user(), course)
    enroll_row(db, make_user(), course, EnrollmentStatus.DROPPED)  # not counted
    make_session(course, status=SessionStatus.LIVE)

    card = client.get(COURSES).json()["items"][0]
    assert card["enrolled_count"] == 2
    assert card["is_live"] is True
    assert "live_session_id" not in card  # only in the detail view, for members


def test_is_enrolled_for_students(client, teacher, make_course, make_user, db):
    mine, other = make_course(teacher, code="A1"), make_course(teacher, code="B1")
    student = make_user()
    enroll_row(db, student, mine)

    cards = login_as(client, student).get(COURSES).json()["items"]
    assert {c["code"]: c["is_enrolled"] for c in cards} == {"A1": True, "B1": False}


@pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.ADMIN])
def test_is_enrolled_is_null_for_other_roles(client, teacher, make_course, make_user, role):
    make_course(teacher)
    card = login_as(client, make_user(role=role)).get(COURSES).json()["items"][0]
    assert card["is_enrolled"] is None


def test_invalid_cookie_is_treated_as_anonymous(client, teacher, make_course):
    make_course(teacher)
    client.cookies.set(ACCESS_TOKEN_COOKIE, "not-a-jwt")
    res = client.get(COURSES)
    assert res.status_code == 200
    assert res.json()["items"][0]["is_enrolled"] is None


def test_next_class_from_timetable(client, teacher, make_course):
    make_course(teacher, schedules=[MONDAY_10_KTM])
    next_at = datetime.fromisoformat(client.get(COURSES).json()["items"][0]["next_class_at"])
    now = datetime.now(UTC)
    assert now < next_at <= now + timedelta(days=7)
    # Monday 10:00 Kathmandu is always Monday 04:15 UTC.
    assert (next_at.weekday(), next_at.hour, next_at.minute) == (0, 4, 15)


def test_next_class_prefers_an_earlier_scheduled_session(client, teacher, make_course, make_session):
    course = make_course(teacher, schedules=[MONDAY_10_KTM])
    soon = (datetime.now(UTC) + timedelta(minutes=30)).replace(microsecond=0)
    make_session(course, scheduled_for=soon)
    make_session(course, scheduled_for=datetime.now(UTC) - timedelta(days=1))  # past: ignored
    next_at = client.get(COURSES).json()["items"][0]["next_class_at"]
    assert datetime.fromisoformat(next_at) == soon


def test_no_next_class_without_timetable_or_sessions(client, teacher, make_course):
    make_course(teacher)
    assert client.get(COURSES).json()["items"][0]["next_class_at"] is None


def test_short_description():
    assert short_description("Short.") == "Short."
    long = "word " * 100
    cut = short_description(long)
    assert len(cut) <= 201 and cut.endswith("…") and not cut.endswith(" …")


# --- detail ----------------------------------------------------------------------


def test_detail(client, make_teacher, make_course, make_session):
    teacher = make_teacher(title="Professor")
    teacher.department, teacher.bio = "Computer Science", "Ten years in industry."
    long_description = "Python fundamentals. " * 30
    course = make_course(teacher, description=long_description, schedules=[MONDAY_10_KTM])
    now = datetime.now(UTC)
    later = make_session(course, scheduled_for=now + timedelta(days=9), title="Week 9")
    sooner = make_session(course, scheduled_for=now + timedelta(days=2), title="Week 8")
    make_session(course, scheduled_for=now - timedelta(days=5), title="Old")  # past
    make_session(course, status=SessionStatus.ENDED, scheduled_for=now + timedelta(days=1))

    res = client.get(f"{COURSES}/{course.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["description"] == long_description
    assert body["short_description"].endswith("…")
    assert body["teacher"]["bio"] == "Ten years in industry."
    assert body["teacher"]["department"] == "Computer Science"
    assert body["schedules"][0]["duration_minutes"] == 60
    assert [s["id"] for s in body["upcoming_sessions"]] == [sooner.id, later.id]
    assert body["live_session_id"] is None


def test_detail_of_unpublished_or_missing_course_is_404(client, teacher, make_course):
    draft = make_course(teacher, is_published=False)
    assert client.get(f"{COURSES}/{draft.id}").status_code == 404
    assert client.get(f"{COURSES}/999").status_code == 404


def test_live_session_id_only_for_members(client, make_teacher, make_course, make_user,
                                         make_session, db):
    teacher, other_teacher = make_teacher(), make_teacher()
    course = make_course(teacher)
    live = make_session(course, status=SessionStatus.LIVE)
    enrolled, outsider, dropped = make_user(), make_user(), make_user()
    enroll_row(db, enrolled, course)
    enroll_row(db, dropped, course, EnrollmentStatus.DROPPED)

    def live_id_for(user):
        if user is None:
            client.cookies.clear()
        else:
            login_as(client, user.user if hasattr(user, "user") else user)
        return client.get(f"{COURSES}/{course.id}").json()["live_session_id"]

    assert live_id_for(None) is None
    assert live_id_for(outsider) is None
    assert live_id_for(dropped) is None
    assert live_id_for(other_teacher) is None
    assert live_id_for(enrolled) == live.id
    assert live_id_for(teacher) == live.id
