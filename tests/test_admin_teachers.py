from datetime import date

import pytest

from app.models import Course, Teacher, User
from tests.conftest import login

TEACHERS = "/api/v1/admin/teachers"


def teacher_body(**overrides):
    body = {
        "email": "anita@example.com",
        "full_name": "Anita Sharma",
        "password": "FirstPass123",
        "title": "Associate Professor",
        "department": "Computer Science",
        "bio": "Teaches programming.",
    }
    return body | overrides


# --- create ------------------------------------------------------------------


def test_create_teacher(admin_client, db):
    res = admin_client.post(TEACHERS, json=teacher_body(email="  Anita@Example.com "))
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "anita@example.com"
    assert body["title"] == "Associate Professor"
    assert body["is_active"] is True
    assert "password" not in body and "hashed_password" not in body

    teacher = db.get(Teacher, body["id"])
    assert teacher.user.role == "teacher"
    assert teacher.user.hashed_password.startswith("$argon2")


def test_created_teacher_can_log_in_as_teacher(admin_client, client):
    admin_client.post(TEACHERS, json=teacher_body())
    client.cookies.clear()  # drop the admin's session
    assert login(client, "anita@example.com", "FirstPass123").status_code == 200
    assert client.get("/api/v1/auth/me").json()["role"] == "teacher"


def test_create_teacher_optional_fields(admin_client):
    body = teacher_body()
    del body["department"], body["bio"]
    res = admin_client.post(TEACHERS, json=body)
    assert res.status_code == 201
    assert res.json()["department"] is None and res.json()["bio"] is None


def test_create_teacher_duplicate_email(admin_client, make_user):
    make_user(email="anita@example.com")  # an existing student
    res = admin_client.post(TEACHERS, json=teacher_body(email="ANITA@example.com"))
    assert res.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"title": "  "},
        {"full_name": ""},
        {"title": None},
    ],
)
def test_create_teacher_invalid(admin_client, overrides):
    assert admin_client.post(TEACHERS, json=teacher_body(**overrides)).status_code == 422


# --- list / get ----------------------------------------------------------------


def test_list_teachers_pagination_search_and_inactive(admin_client, make_teacher):
    make_teacher(email="zoe@example.com", is_active=False)
    for i in range(3):
        make_teacher(email=f"t{i}@example.com")

    res = admin_client.get(TEACHERS, params={"page_size": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 4  # the deactivated teacher is included
    assert len(body["items"]) == 2 and body["page"] == 1

    page2 = admin_client.get(TEACHERS, params={"page_size": 2, "page": 2}).json()
    assert len(page2["items"]) == 2
    first_ids = {t["id"] for t in body["items"]}
    assert first_ids.isdisjoint(t["id"] for t in page2["items"])

    found = admin_client.get(TEACHERS, params={"search": "ZOE@"}).json()
    assert [t["email"] for t in found["items"]] == ["zoe@example.com"]
    assert found["items"][0]["is_active"] is False


def test_list_excludes_admins_and_students(admin_client, make_user):
    make_user()  # student
    assert admin_client.get(TEACHERS).json()["total"] == 0


def test_get_teacher(admin_client, make_teacher):
    teacher = make_teacher(title="Professor")
    res = admin_client.get(f"{TEACHERS}/{teacher.id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Professor"
    assert res.json()["user_id"] == teacher.user_id


def test_get_missing_teacher(admin_client):
    assert admin_client.get(f"{TEACHERS}/999").status_code == 404


# --- update --------------------------------------------------------------------


def test_update_changes_only_sent_fields(admin_client, make_teacher):
    teacher = make_teacher(title="Lecturer")
    admin_client.patch(f"{TEACHERS}/{teacher.id}", json={"bio": "Old bio", "department": "Math"})

    res = admin_client.patch(f"{TEACHERS}/{teacher.id}", json={"title": "Professor", "bio": None})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Professor"
    assert body["bio"] is None  # explicit null clears a nullable field
    assert body["department"] == "Math"  # not sent, so unchanged
    assert body["full_name"] == teacher.user.full_name


def test_update_rejects_null_for_required_fields(admin_client, make_teacher):
    teacher = make_teacher()
    for field in ("title", "full_name", "email", "is_active"):
        res = admin_client.patch(f"{TEACHERS}/{teacher.id}", json={field: None})
        assert res.status_code == 422, field


def test_update_email_conflict(admin_client, make_teacher, make_user):
    make_user(email="taken@example.com")
    teacher = make_teacher()
    res = admin_client.patch(f"{TEACHERS}/{teacher.id}", json={"email": "taken@example.com"})
    assert res.status_code == 409


def test_password_reset(admin_client, client, make_teacher):
    teacher = make_teacher()
    email = teacher.user.email
    admin_client.patch(f"{TEACHERS}/{teacher.id}", json={"password": "BrandNew456"})
    client.cookies.clear()
    assert login(client, email, "BrandNew456").status_code == 200


def test_deactivation_ends_existing_sessions(admin_client, make_teacher, override_get_db):
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    teacher = make_teacher()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="https://testserver") as teacher_client:
        login(teacher_client, teacher.user.email)
        assert teacher_client.get("/api/v1/auth/me").status_code == 200

        res = admin_client.patch(f"{TEACHERS}/{teacher.id}", json={"is_active": False})
        assert res.json()["is_active"] is False

        assert teacher_client.get("/api/v1/auth/me").status_code == 401
        assert login(teacher_client, teacher.user.email).status_code == 403


def test_update_missing_teacher(admin_client):
    assert admin_client.patch(f"{TEACHERS}/999", json={"title": "X"}).status_code == 404


# --- delete --------------------------------------------------------------------


def test_delete_teacher_removes_account(admin_client, make_teacher, db):
    teacher = make_teacher()
    teacher_id, user_id = teacher.id, teacher.user_id
    assert admin_client.delete(f"{TEACHERS}/{teacher_id}").status_code == 204
    db.expire_all()
    assert db.get(Teacher, teacher_id) is None
    assert db.get(User, user_id) is None
    assert admin_client.get(f"{TEACHERS}/{teacher_id}").status_code == 404


def test_delete_teacher_with_courses_is_refused(admin_client, make_teacher, db):
    teacher = make_teacher()
    db.add(Course(code="CS101", title="Intro", teacher=teacher,
                  starts_on=date(2026, 9, 1), ends_on=date(2026, 12, 1)))
    db.commit()
    res = admin_client.delete(f"{TEACHERS}/{teacher.id}")
    assert res.status_code == 409
    assert "1 course" in res.json()["detail"]


def test_delete_missing_teacher(admin_client):
    assert admin_client.delete(f"{TEACHERS}/999").status_code == 404
