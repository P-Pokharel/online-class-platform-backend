import pytest

from app.models import Enrollment, EnrollmentStatus, SessionStatus, UserRole
from tests.conftest import login_as

MY_COURSES = "/api/v1/teacher/courses"


def students_url(course_id):
    return f"/api/v1/teacher/courses/{course_id}/students"


def test_lists_only_own_courses_including_unpublished(
    client, make_teacher, make_course, make_user, make_session, db
):
    me, someone_else = make_teacher(), make_teacher()
    published = make_course(me, code="CS101")
    make_course(me, code="CS900", is_published=False)
    make_course(someone_else, code="MATH201")
    db.add(Enrollment(student=make_user(), course=published))
    db.commit()
    live = make_session(published, status=SessionStatus.LIVE)

    res = login_as(client, me.user).get(MY_COURSES)
    assert res.status_code == 200
    courses = {c["code"]: c for c in res.json()}
    assert set(courses) == {"CS101", "CS900"}
    assert courses["CS900"]["is_published"] is False
    assert courses["CS101"]["enrolled_count"] == 1
    assert courses["CS101"]["is_live"] is True
    assert courses["CS101"]["live_session_id"] == live.id


def test_students_of_own_course(client, make_teacher, make_course, make_user, db):
    teacher = make_teacher()
    course = make_course(teacher)
    zara, adam, gone = make_user(), make_user(), make_user()
    zara.full_name, adam.full_name = "Zara Khan", "Adam Rai"
    db.add_all([
        Enrollment(student=zara, course=course),
        Enrollment(student=adam, course=course),
        Enrollment(student=gone, course=course, status=EnrollmentStatus.DROPPED),
    ])
    db.commit()

    res = login_as(client, teacher.user).get(students_url(course.id))
    assert res.status_code == 200
    assert [s["full_name"] for s in res.json()] == ["Adam Rai", "Zara Khan"]
    assert set(res.json()[0]) == {"id", "full_name", "email", "enrolled_at"}


def test_students_of_someone_elses_course_is_403(client, make_teacher, make_course):
    me, owner = make_teacher(), make_teacher()
    course = make_course(owner)
    assert login_as(client, me.user).get(students_url(course.id)).status_code == 403


def test_students_of_missing_course_is_404(client, make_teacher):
    assert login_as(client, make_teacher().user).get(students_url(999)).status_code == 404


def test_teacher_account_without_profile(client, make_user, make_teacher, make_course):
    course = make_course(make_teacher())
    profileless = make_user(role=UserRole.TEACHER)
    login_as(client, profileless)
    assert client.get(MY_COURSES).json() == []
    assert client.get(students_url(course.id)).status_code == 403


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.ADMIN])
def test_other_roles_get_403(client, make_user, role):
    login_as(client, make_user(role=role))
    assert client.get(MY_COURSES).status_code == 403
    assert client.get(students_url(1)).status_code == 403


def test_anonymous_gets_401(client):
    assert client.get(MY_COURSES).status_code == 401
    assert client.get(students_url(1)).status_code == 401
