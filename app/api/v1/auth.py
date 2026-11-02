from fastapi import APIRouter, HTTPException, Response, status

from app.core.config import settings
from app.core.deps import ACCESS_TOKEN_COOKIE, CurrentUser, DbSession
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> UserOut:
    """Create a student account."""
    try:
        user = auth_service.register_student(
            db, email=body.email, password=body.password, full_name=body.full_name
        )
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "email is already registered")
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: DbSession) -> UserOut:
    """Check credentials and set the JWT as an httpOnly cookie."""
    try:
        user = auth_service.authenticate(db, body.email, body.password)
    except auth_service.InactiveUser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=create_access_token(user.id, user.role),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Remove the cookie from the browser."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
