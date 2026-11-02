from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.models.enums import UserRole

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)

ALGORITHM = "HS256"
ISSUER = "online-class-platform"

AUDIENCE_STUDENT = "student-api"
AUDIENCE_TEACHER = "teacher-api"
AUDIENCE_ADMIN = "admin-api"

# A list per role, so a role can be granted more than one API area later
# without changing the token format.
ROLE_AUDIENCES: dict[UserRole, list[str]] = {
    UserRole.STUDENT: [AUDIENCE_STUDENT],
    UserRole.TEACHER: [AUDIENCE_TEACHER],
    UserRole.ADMIN: [AUDIENCE_ADMIN],
}
ALL_AUDIENCES = sorted({aud for auds in ROLE_AUDIENCES.values() for aud in auds})


def create_access_token(
    user_id: int, role: UserRole, expires_delta: timedelta | None = None
) -> str:
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    claims = {
        "iss": ISSUER,
        "sub": str(user_id),
        "aud": ROLE_AUDIENCES[role],
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature, expiry, issuer, and audience; return the claims."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[ALGORITHM],
        audience=ALL_AUDIENCES,
        issuer=ISSUER,
        options={"require": ["iss", "sub", "aud", "iat", "exp"]},
    )
