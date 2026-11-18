"""Every admin endpoint must refuse anonymous users (401) and non-admins (403)."""
import pytest

from app.models import UserRole
from tests.conftest import login

ADMIN_ENDPOINTS = [
    ("POST", "/api/v1/admin/teachers"),
    ("GET", "/api/v1/admin/teachers"),
    ("GET", "/api/v1/admin/teachers/1"),
    ("PATCH", "/api/v1/admin/teachers/1"),
    ("DELETE", "/api/v1/admin/teachers/1"),
    ("POST", "/api/v1/admin/courses"),
    ("GET", "/api/v1/admin/courses"),
    ("GET", "/api/v1/admin/courses/1"),
    ("PATCH", "/api/v1/admin/courses/1"),
    ("DELETE", "/api/v1/admin/courses/1"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
def test_anonymous_gets_401(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
def test_non_admin_gets_403(client, make_user, role, method, path):
    user = make_user(role=role)
    login(client, user.email)
    # 403 comes from the router dependency, before the body is even validated.
    assert client.request(method, path, json={}).status_code == 403


def test_admin_route_list_is_complete(client):
    """Fail if an admin route is added without being covered by the tests above."""
    paths = client.get("/openapi.json").json()["paths"]
    routes = {
        (method.upper(), path.replace("{teacher_id}", "1").replace("{course_id}", "1"))
        for path, ops in paths.items()
        if path.startswith("/api/v1/admin/")
        for method in ops
    }
    assert routes == set(ADMIN_ENDPOINTS)
