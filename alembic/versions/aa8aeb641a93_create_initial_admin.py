"""create initial admin

Revision ID: aa8aeb641a93
Revises: eed73ebe846e
Create Date: 2026-10-13 22:54:29.752362

Creates the first admin account from ADMIN_EMAIL, ADMIN_PASSWORD and
ADMIN_FULL_NAME in .env. Nobody can register as an admin, so this is the only
way in. Like every migration, it runs once per database: changing the .env
values afterwards does not change the admin.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.config import settings
from app.core.security import hash_password


# revision identifiers, used by Alembic.
revision: str = 'aa8aeb641a93'
down_revision: Union[str, Sequence[str], None] = 'eed73ebe846e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIN_PASSWORD_LENGTH = 8
users = sa.table(
    "users",
    sa.column("id", sa.Integer),
    sa.column("email", sa.String),
    sa.column("full_name", sa.String),
    sa.column("hashed_password", sa.String),
    sa.column("role", sa.String),
)


def _admin_email() -> str:
    if not settings.admin_email or not settings.admin_password:
        raise RuntimeError(
            "ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env to create the "
            "first admin account. See .env.example."
        )
    return settings.admin_email.strip().lower()


def upgrade() -> None:
    """Insert the admin user, unless a user with that email already exists."""
    email = _admin_email()
    if len(settings.admin_password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(
            f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    conn = op.get_bind()
    existing = conn.execute(
        sa.select(users.c.id).where(users.c.email == email)
    ).first()
    if existing:
        print(f"User {email} already exists; not creating an admin.")
        return

    op.bulk_insert(
        users,
        [
            {
                "email": email,
                "full_name": settings.admin_full_name,
                "hashed_password": hash_password(settings.admin_password),
                "role": "admin",
            }
        ],
    )


def downgrade() -> None:
    """Delete the admin user created by upgrade()."""
    email = _admin_email()
    op.execute(
        users.delete().where(users.c.email == email, users.c.role == "admin")
    )
