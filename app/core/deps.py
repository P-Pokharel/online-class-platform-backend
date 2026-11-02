from collections.abc import Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import (
    AUDIENCE_ADMIN,
    AUDIENCE_STUDENT,
    AUDIENCE_TEACHER,
    ROLE_AUDIENCES,
    decode_access_token,
)
from app.db.session import get_db
from app.models import User

ACCESS_TOKEN_COOKIE = "access_token"

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_token_claims(request: Request) -> dict[str, Any]:
    """Read the JWT from the httpOnly cookie and verify it. 401 if missing or invalid."""
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        raise _unauthorized()
    try:
        return decode_access_token(token)
    except jwt.InvalidTokenError:
        # Expired, bad signature, wrong issuer/audience, malformed: all the same
        # to the client. The reason isn't exposed.
        raise _unauthorized("Invalid or expired token")


TokenClaims = Annotated[dict[str, Any], Depends(get_token_claims)]


def get_current_user(claims: TokenClaims, db: DbSession) -> User:
    """Load the user the token belongs to."""
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized()
    if sorted(claims["aud"]) != sorted(ROLE_AUDIENCES[user.role]):
        raise _unauthorized("Token no longer matches your role; please log in again")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_audience(audience: str) -> Callable[..., User]:
    """Build a dependency that allows only tokens issued for `audience`.

    401 means "we don't know who you are" (no or bad token); 403 means "we
    know who you are, but this token isn't meant for this part of the API".
    """

    def dependency(claims: TokenClaims, user: CurrentUser) -> User:
        if audience not in claims["aud"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed for your role",
            )
        return user

    return dependency


require_student = require_audience(AUDIENCE_STUDENT)
require_teacher = require_audience(AUDIENCE_TEACHER)
require_admin = require_audience(AUDIENCE_ADMIN)

StudentUser = Annotated[User, Depends(require_student)]
TeacherUser = Annotated[User, Depends(require_teacher)]
AdminUser = Annotated[User, Depends(require_admin)]
