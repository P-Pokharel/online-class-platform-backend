from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.deps import ACCESS_TOKEN_COOKIE
from app.core.security import (
    ALGORITHM,
    AUDIENCE_ADMIN,
    AUDIENCE_STUDENT,
    AUDIENCE_TEACHER,
    ISSUER,
    create_access_token,
)
from app.models import User, UserRole
from tests.conftest import TEST_PASSWORD, login

REGISTER = "/api/v1/auth/register"
ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"


def register(client, **overrides):
    body = {"email": "ram@example.com", "password": "Password123", "full_name": "Ram Thapa"}
    return client.post(REGISTER, json=body | overrides)


def decode_cookie_token(client) -> dict:
    token = client.cookies[ACCESS_TOKEN_COOKIE]
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[ALGORITHM], options={"verify_aud": False}
    )


# --- register ----------------------------------------------------------------


def test_register_creates_student(client, db):
    res = register(client)
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "ram@example.com"
    assert body["role"] == "student"
    assert "password" not in body and "hashed_password" not in body

    user = db.get(User, body["id"])
    assert user.hashed_password.startswith("$argon2")


def test_register_ignores_requested_role(client):
    res = register(client, role="admin")
    assert res.status_code == 201
    assert res.json()["role"] == "student"


def test_register_duplicate_email_is_case_insensitive(client):
    assert register(client).status_code == 201
    res = register(client, email="  RAM@Example.com ")
    assert res.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"full_name": "   "},
    ],
)
def test_register_rejects_invalid_input(client, overrides):
    assert register(client, **overrides).status_code == 422


# --- login -------------------------------------------------------------------


def test_login_sets_httponly_cookie_and_hides_token(client, make_user):
    user = make_user(email="sita@example.com")
    res = login(client, "Sita@Example.com")
    assert res.status_code == 200
    assert res.json() == {
        "id": user.id,
        "email": "sita@example.com",
        "full_name": user.full_name,
        "role": "student",
    }

    cookie = res.headers["set-cookie"].lower()
    assert cookie.startswith(f"{ACCESS_TOKEN_COOKIE}=")
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    # The token travels only in the cookie, never in the body.
    assert client.cookies[ACCESS_TOKEN_COOKIE] not in res.text


@pytest.mark.parametrize(
    ("role", "audience"),
    [
        (UserRole.STUDENT, AUDIENCE_STUDENT),
        (UserRole.TEACHER, AUDIENCE_TEACHER),
        (UserRole.ADMIN, AUDIENCE_ADMIN),
    ],
)
def test_login_token_audience_matches_role(client, make_user, role, audience):
    user = make_user(role=role)
    assert login(client, user.email).status_code == 200

    claims = decode_cookie_token(client)
    assert claims["aud"] == [audience]
    assert claims["sub"] == str(user.id)
    assert claims["iss"] == ISSUER
    assert claims["exp"] - claims["iat"] == settings.access_token_expire_minutes * 60


def test_login_wrong_password(client, make_user):
    user = make_user()
    res = login(client, user.email, "WrongPassword1")
    assert res.status_code == 401
    assert ACCESS_TOKEN_COOKIE not in client.cookies


def test_login_unknown_email_gives_same_error(client, make_user):
    user = make_user()
    wrong_password = login(client, user.email, "WrongPassword1")
    unknown_email = login(client, "nobody@example.com")
    assert unknown_email.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_login_inactive_user(client, make_user):
    user = make_user(is_active=False)
    assert login(client, user.email).status_code == 403
    # Without the right password, a disabled account looks like any failed login.
    assert login(client, user.email, "WrongPassword1").status_code == 401


# --- me ----------------------------------------------------------------------


def test_me_without_cookie(client):
    assert client.get(ME).status_code == 401


def test_me_with_cookie(client, make_user):
    user = make_user(role=UserRole.TEACHER)
    login(client, user.email)
    res = client.get(ME)
    assert res.status_code == 200
    assert res.json()["id"] == user.id
    assert res.json()["role"] == "teacher"


def test_register_then_login_then_me(client):
    register(client)
    assert login(client, "ram@example.com", "Password123").status_code == 200
    assert client.get(ME).json()["email"] == "ram@example.com"


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda uid: "not-a-jwt", id="garbage"),
        pytest.param(
            lambda uid: create_access_token(uid, UserRole.STUDENT, timedelta(seconds=-1)),
            id="expired",
        ),
        pytest.param(
            lambda uid: jwt.encode(
                {"iss": ISSUER, "sub": str(uid), "aud": [AUDIENCE_ADMIN], "iat": 0, "exp": 2**31},
                "some-other-secret-that-is-long-enough!!",
                algorithm=ALGORITHM,
            ),
            id="wrong-signature",
        ),
        pytest.param(
            lambda uid: jwt.encode(
                {"iss": "someone-else", "sub": str(uid), "aud": [AUDIENCE_STUDENT], "iat": 0, "exp": 2**31},
                settings.jwt_secret_key,
                algorithm=ALGORITHM,
            ),
            id="wrong-issuer",
        ),
        pytest.param(
            lambda uid: jwt.encode(
                {"iss": ISSUER, "sub": str(uid), "aud": ["unknown-api"], "iat": 0, "exp": 2**31},
                settings.jwt_secret_key,
                algorithm=ALGORITHM,
            ),
            id="unknown-audience",
        ),
        pytest.param(
            lambda uid: jwt.encode(
                {"iss": ISSUER, "sub": str(uid), "aud": [AUDIENCE_STUDENT], "exp": 2**31},
                settings.jwt_secret_key,
                algorithm=ALGORITHM,
            ),
            id="missing-iat",
        ),
    ],
)
def test_me_rejects_bad_tokens(client, make_user, token_factory):
    user = make_user()
    client.cookies.set(ACCESS_TOKEN_COOKIE, token_factory(user.id))
    assert client.get(ME).status_code == 401


def test_me_rejects_deactivated_user(client, make_user, db):
    user = make_user()
    login(client, user.email)
    user.is_active = False
    db.commit()
    assert client.get(ME).status_code == 401


# --- logout ------------------------------------------------------------------


def test_logout_clears_cookie(client, make_user):
    user = make_user()
    login(client, user.email, TEST_PASSWORD)
    assert client.get(ME).status_code == 200

    res = client.post(LOGOUT)
    assert res.status_code == 204
    assert ACCESS_TOKEN_COOKIE not in client.cookies
    assert client.get(ME).status_code == 401


def test_login_accepts_email_that_registration_would_reject(client, make_user):
    # Accounts created by an admin or a migration may use domains that strict
    # email validation rejects (e.g. reserved ".test" names).
    user = make_user(email="anita@school.test")
    assert login(client, "Anita@School.test").status_code == 200
