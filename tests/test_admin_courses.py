from datetime import date

import pytest

from app.models import ClassSession, Course, CourseSchedule, Enrollment

COURSES = "/api/v1/admin/courses"

MONDAY_10 = {"day_of_week": 0, "start_time": "10:00:00", "duration_minutes": 90,
             "timezone": "Asia/Kathmandu"}
WEDNESDAY_10 = MONDAY_10 | {"day_of_week": 2}


@pytest.fixture
def teacher(make_teacher):
    return make_teacher(title="Associate Professor")


def course_body(teacher_id, **overrides):
    body = {
        "code": "cs101",
        "title": "Introduction to Programming",
        "description": "Python fundamentals.",
        "teacher_id": teacher_id,
        "price_cents": 4999,
        "starts_on": "2026-09-01",
        "ends_on": "2026-12-20",
        "schedules": [WEDNESDAY_10, MONDAY_10],
    }
    return body | overrides


def create(admin_client, teacher_id, **overrides):
    res = admin_client.post(COURSES, json=course_body(teacher_id, **overrides))
    assert res.status_code == 201, res.text
    return res.json()


# --- create --------------------------------------------------------------------


def test_create_course(admin_client, teacher):
    body = create(admin_client, teacher.id)
    assert body["code"] == "CS101"  # normalized to upper case
    assert body["is_published"] is False  # drafts by default
    assert body["teacher"] == {
        "id": teacher.id, "full_name": teacher.user.full_name, "title": "Associate Professor",
    }
    # Sorted by weekday, whatever order they were sent in.
    assert [s["day_of_week"] for s in body["schedules"]] == [0, 2]
    assert body["schedules"][0]["start_time"] == "10:00:00"


def test_create_course_without_schedules(admin_client, teacher):
    assert create(admin_client, teacher.id, schedules=[])["schedules"] == []


def test_create_course_duplicate_code(admin_client, teacher):
    create(admin_client, teacher.id)
    res = admin_client.post(COURSES, json=course_body(teacher.id, code="CS101"))
    assert res.status_code == 409


def test_create_course_unknown_teacher(admin_client):
    res = admin_client.post(COURSES, json=course_body(999))
    assert res.status_code == 400
    assert "does not exist" in res.json()["detail"]


def test_create_course_deactivated_teacher(admin_client, make_teacher):
    inactive = make_teacher(is_active=False)
    res = admin_client.post(COURSES, json=course_body(inactive.id))
    assert res.status_code == 400
    assert "deactivated" in res.json()["detail"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"ends_on": "2026-08-01"},  # before starts_on
        {"price_cents": -1},
        {"code": "C"},
        {"code": "CS 101"},
        {"title": ""},
        {"schedules": [MONDAY_10 | {"day_of_week": 7}]},
        {"schedules": [MONDAY_10 | {"duration_minutes": 0}]},
        {"schedules": [MONDAY_10 | {"timezone": "Mars/Olympus"}]},
        {"schedules": [MONDAY_10 | {"start_time": "25:00"}]},
    ],
)
def test_create_course_invalid(admin_client, teacher, overrides):
    assert admin_client.post(COURSES, json=course_body(teacher.id, **overrides)).status_code == 422


# --- list / get ----------------------------------------------------------------


def test_list_courses_filters_and_pagination(admin_client, make_teacher):
    t1, t2 = make_teacher(), make_teacher()
    create(admin_client, t1.id, code="CS101", title="Intro to Programming", is_published=True)
    create(admin_client, t1.id, code="CS201", title="Data Structures")
    create(admin_client, t2.id, code="MATH201", title="Linear Algebra", is_published=True)

    everything = admin_client.get(COURSES).json()
    assert everything["total"] == 3  # unpublished included
    assert [c["code"] for c in everything["items"]] == ["CS101", "CS201", "MATH201"]

    def codes(**params):
        return [c["code"] for c in admin_client.get(COURSES, params=params).json()["items"]]

    assert codes(is_published=False) == ["CS201"]
    assert codes(teacher_id=t2.id) == ["MATH201"]
    assert codes(search="algebra") == ["MATH201"]
    assert codes(search="cs") == ["CS101", "CS201"]
    page = admin_client.get(COURSES, params={"page": 2, "page_size": 2}).json()
    assert [c["code"] for c in page["items"]] == ["MATH201"] and page["total"] == 3


def test_get_course(admin_client, teacher):
    created = create(admin_client, teacher.id)
    res = admin_client.get(f"{COURSES}/{created['id']}")
    assert res.status_code == 200
    assert res.json() == created


def test_get_missing_course(admin_client):
    assert admin_client.get(f"{COURSES}/999").status_code == 404


# --- update --------------------------------------------------------------------


def test_update_partial_and_publish(admin_client, teacher):
    created = create(admin_client, teacher.id)
    res = admin_client.patch(f"{COURSES}/{created['id']}",
                             json={"title": "Programming 1", "is_published": True})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Programming 1" and body["is_published"] is True
    assert body["price_cents"] == 4999 and len(body["schedules"]) == 2  # untouched


def test_update_replaces_schedules(admin_client, teacher, db):
    created = create(admin_client, teacher.id)
    friday = MONDAY_10 | {"day_of_week": 4, "start_time": "14:30:00"}
    body = admin_client.patch(f"{COURSES}/{created['id']}", json={"schedules": [friday]}).json()
    assert [(s["day_of_week"], s["start_time"]) for s in body["schedules"]] == [(4, "14:30:00")]
    # The old rows are gone from the database, not just from the response.
    assert db.query(CourseSchedule).count() == 1


def test_update_reassigns_teacher(admin_client, make_teacher):
    t1, t2 = make_teacher(), make_teacher(title="Professor")
    created = create(admin_client, t1.id)
    body = admin_client.patch(f"{COURSES}/{created['id']}", json={"teacher_id": t2.id}).json()
    assert body["teacher"]["id"] == t2.id and body["teacher"]["title"] == "Professor"


def test_update_to_unknown_teacher(admin_client, teacher):
    created = create(admin_client, teacher.id)
    res = admin_client.patch(f"{COURSES}/{created['id']}", json={"teacher_id": 999})
    assert res.status_code == 400


def test_update_dates_checked_against_stored_values(admin_client, teacher):
    created = create(admin_client, teacher.id)  # 2026-09-01 .. 2026-12-20
    res = admin_client.patch(f"{COURSES}/{created['id']}", json={"ends_on": "2026-08-31"})
    assert res.status_code == 422
    assert admin_client.get(f"{COURSES}/{created['id']}").json()["ends_on"] == "2026-12-20"


def test_update_code_conflict(admin_client, teacher):
    create(admin_client, teacher.id, code="CS101")
    other = create(admin_client, teacher.id, code="CS201")
    assert admin_client.patch(f"{COURSES}/{other['id']}", json={"code": "cs101"}).status_code == 409


def test_update_rejects_null_for_required_fields(admin_client, teacher):
    created = create(admin_client, teacher.id)
    for field in ("title", "code", "teacher_id", "starts_on", "schedules", "is_published"):
        res = admin_client.patch(f"{COURSES}/{created['id']}", json={field: None})
        assert res.status_code == 422, field


def test_update_missing_course(admin_client):
    assert admin_client.patch(f"{COURSES}/999", json={"title": "X"}).status_code == 404


# --- delete --------------------------------------------------------------------


def test_delete_course_and_its_schedules(admin_client, teacher, db):
    created = create(admin_client, teacher.id)
    assert admin_client.delete(f"{COURSES}/{created['id']}").status_code == 204
    assert admin_client.get(f"{COURSES}/{created['id']}").status_code == 404
    assert db.query(CourseSchedule).count() == 0


def test_delete_course_with_enrollment_is_refused(admin_client, teacher, make_user, db):
    created = create(admin_client, teacher.id)
    db.add(Enrollment(student=make_user(), course_id=created["id"]))
    db.commit()
    res = admin_client.delete(f"{COURSES}/{created['id']}")
    assert res.status_code == 409
    assert "unpublish" in res.json()["detail"]


def test_delete_course_with_class_session_is_refused(admin_client, teacher, db):
    created = create(admin_client, teacher.id)
    db.add(ClassSession(course_id=created["id"], title="Week 1"))
    db.commit()
    assert admin_client.delete(f"{COURSES}/{created['id']}").status_code == 409


def test_delete_missing_course(admin_client):
    assert admin_client.delete(f"{COURSES}/999").status_code == 404


def test_teacher_with_course_cannot_be_deleted_until_course_is(admin_client, teacher, db):
    created = create(admin_client, teacher.id)
    assert admin_client.delete(f"/api/v1/admin/teachers/{teacher.id}").status_code == 409
    admin_client.delete(f"{COURSES}/{created['id']}")
    assert admin_client.delete(f"/api/v1/admin/teachers/{teacher.id}").status_code == 204
    assert db.query(Course).count() == 0
