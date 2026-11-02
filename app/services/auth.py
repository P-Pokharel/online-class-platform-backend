from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.models import User, UserRole


class EmailAlreadyRegistered(Exception):
    pass


class InactiveUser(Exception):
    pass


def register_student(db: Session, email: str, password: str, full_name: str) -> User:
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole.STUDENT,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered(email)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email and password match, otherwise None."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)  # equalize response time
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        raise InactiveUser(email)
    return user
