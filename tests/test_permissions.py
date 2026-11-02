"""Role permissions via the JWT `aud` claim.

No real endpoint needs a specific role yet, so these tests mount the
require_* dependencies on a small throwaway app.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import ACCESS_TOKEN_COOKIE, AdminUser, StudentUser, TeacherUser
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import UserRole
from tests.conftest import login

probe = FastAPI()


@probe.get("/student-only")
def student_only(user: StudentUser):
    return {"id": user.id}


@probe.get("/teacher-only")
def teacher_only(user: TeacherUser):
    return {"id": user.id}


@probe.get("/admin-only")
def admin_only(user: AdminUser):
    return {"id": user.id}


ROUTE_FOR_ROLE = {
    UserRole.STUDENT: "/student-only",
    UserRole.TEACHER: "/teacher-only",
    UserRole.ADMIN: "/admin-only",
}


@pytest.fixture
def probe_client(override_get_db):
    probe.dependency_overrides[get_db] = override_get_db
    with TestClient(probe, base_url="https://testserver") as c:
        yield c
    probe.dependency_overrides.clear()


def as_user(probe_client, user):
    probe_client.cookies.set(ACCESS_TOKEN_COOKIE, create_access_token(user.id, user.role))
    return probe_client


@pytest.mark.parametrize("route", ROUTE_FOR_ROLE.values())
def test_no_cookie_is_401(probe_client, route):
    assert probe_client.get(route).status_code == 401


@pytest.mark.parametrize("user_role", list(UserRole))
@pytest.mark.parametrize("route_role", list(UserRole))
def test_each_role_reaches_only_its_own_routes(probe_client, make_user, user_role, route_role):
    client = as_user(probe_client, make_user(role=user_role))
    expected = 200 if user_role == route_role else 403
    assert client.get(ROUTE_FOR_ROLE[route_role]).status_code == expected


def test_cookie_from_real_login_works(client, probe_client, make_user):
    teacher = make_user(role=UserRole.TEACHER)
    login(client, teacher.email)
    probe_client.cookies.set(ACCESS_TOKEN_COOKIE, client.cookies[ACCESS_TOKEN_COOKIE])
    assert probe_client.get("/teacher-only").status_code == 200
    assert probe_client.get("/student-only").status_code == 403


def test_token_is_rejected_after_role_change(probe_client, make_user, db):
    # The token still says "teacher-api", but the user is no longer a teacher.
    user = make_user(role=UserRole.TEACHER)
    client = as_user(probe_client, user)
    user.role = UserRole.STUDENT
    db.commit()
    assert client.get("/teacher-only").status_code == 401
    assert client.get("/student-only").status_code == 401
