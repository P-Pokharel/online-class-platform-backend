from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Enrollment, SessionStatus, UserRole
from tests.conftest import login_as

MY_COURSES = "/api/v1/me/courses"


def enroll_url(course_id):
    return f"/api/v1/courses/{course_id}/enroll"


def drop_url(course_id):
    return f"/api/v1/courses/{course_id}/drop"


@pytest.fixture
def course(make_teacher, make_course):
    return make_course(make_teacher(), code="CS101")


@pytest.fixture
def student(make_user):
    return make_user()


@pytest.fixture
def student_client(client, student):
    return login_as(client, student)


def test_enroll(student_client, course):
    res = student_client.post(enroll_url(course.id))
    assert res.status_code == 200
    assert res.json()["course_id"] == course.id
    assert res.json()["status"] == "active"
    assert res.json()["enrolled_at"]

    card = student_client.get("/api/v1/courses").json()["items"][0]
    assert card["is_enrolled"] is True and card["enrolled_count"] == 1


def test_double_enroll_is_409(student_client, course):
    student_client.post(enroll_url(course.id))
    assert student_client.post(enroll_url(course.id)).status_code == 409


def test_drop_and_reenroll_reuses_the_row(student_client, course, student, db):
    first = student_client.post(enroll_url(course.id)).json()

    res = student_client.post(drop_url(course.id))
    assert res.status_code == 200 and res.json()["status"] == "dropped"
    assert student_client.get(MY_COURSES).json() == []

    again = student_client.post(enroll_url(course.id))
    assert again.status_code == 200 and again.json()["status"] == "active"
    assert again.json()["enrolled_at"] >= first["enrolled_at"]
    rows = db.scalars(select(Enrollment).where(Enrollment.student_id == student.id)).all()
    assert len(rows) == 1  # one row per (student, course)


def test_drop_when_not_enrolled_is_409(student_client, course):
    assert student_client.post(drop_url(course.id)).status_code == 409
    student_client.post(enroll_url(course.id))
    student_client.post(drop_url(course.id))
    assert student_client.post(drop_url(course.id)).status_code == 409  # already dropped


def test_missing_or_unpublished_course_is_404(student_client, make_teacher, make_course):
    draft = make_course(make_teacher(), is_published=False)
    assert student_client.post(enroll_url(draft.id)).status_code == 404
    assert student_client.post(enroll_url(999)).status_code == 404
    assert student_client.post(drop_url(999)).status_code == 404


def test_ended_course_is_409(student_client, make_teacher, make_course):
    yesterday = date.today() - timedelta(days=1)
    ended = make_course(make_teacher(), starts_on=yesterday - timedelta(days=90), ends_on=yesterday)
    res = student_client.post(enroll_url(ended.id))
    assert res.status_code == 409
    assert "ended" in res.json()["detail"]


@pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.ADMIN])
def test_only_students_can_enroll(client, make_user, course, role):
    login_as(client, make_user(role=role))
    assert client.post(enroll_url(course.id)).status_code == 403
    assert client.post(drop_url(course.id)).status_code == 403
    assert client.get(MY_COURSES).status_code == 403


def test_anonymous_gets_401(client, course):
    assert client.post(enroll_url(course.id)).status_code == 401
    assert client.post(drop_url(course.id)).status_code == 401
    assert client.get(MY_COURSES).status_code == 401


# --- my courses --------------------------------------------------------------------


def test_my_courses(student_client, make_teacher, make_course, make_session, db):
    teacher = make_teacher(title="Professor")
    b = make_course(teacher, code="B200")
    a = make_course(teacher, code="A100")
    make_course(teacher, code="C300")  # not enrolled
    live = make_session(b, status=SessionStatus.LIVE)
    student_client.post(enroll_url(b.id))
    student_client.post(enroll_url(a.id))

    res = student_client.get(MY_COURSES)
    assert res.status_code == 200
    courses = res.json()
    assert [c["code"] for c in courses] == ["A100", "B200"]
    assert courses[0]["live_session_id"] is None
    assert courses[1]["live_session_id"] == live.id and courses[1]["is_live"] is True
    assert all(c["is_enrolled"] is True and c["enrolled_at"] for c in courses)
    assert courses[0]["teacher"]["title"] == "Professor"


def test_my_courses_keeps_courses_unpublished_after_enrolling(student_client, course, db):
    student_client.post(enroll_url(course.id))
    course.is_published = False
    db.commit()
    assert [c["code"] for c in student_client.get(MY_COURSES).json()] == ["CS101"]
    # Dropping still works, even though the course is no longer in the catalog.
    assert student_client.post(drop_url(course.id)).status_code == 200
