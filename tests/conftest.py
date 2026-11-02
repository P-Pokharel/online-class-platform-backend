from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import User, UserRole

TEST_PASSWORD = "Password123"


def _test_database_url() -> str:
    """Return TEST_DATABASE_URL, refusing anything that could be the real database.

    The suite drops every table, so pointing it at the dev database would wipe it.
    """
    url = settings.test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set in .env", returncode=1)
    test_db = make_url(url).database or ""
    if test_db == make_url(settings.database_url).database or not test_db.endswith("_test"):
        pytest.exit(
            f"Refusing to run tests against database {test_db!r}: "
            "TEST_DATABASE_URL must name a separate database ending in '_test'.",
            returncode=1,
        )
    return url


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(_test_database_url())
    # Tests build tables straight from the models. Migrations are checked
    # separately by `alembic upgrade head`.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    yield sessionmaker(engine, expire_on_commit=False)
    # Empty every table after each test so tests can't affect each other.
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def override_get_db(session_factory: sessionmaker[Session]) -> Callable[[], Iterator[Session]]:
    def _get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    return _get_db


@pytest.fixture
def client(override_get_db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = override_get_db
    # https base URL: the auth cookie is Secure, and the client (like a browser)
    # won't send Secure cookies over plain http.
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    counter = 0

    def _make_user(
        role: UserRole = UserRole.STUDENT,
        email: str | None = None,
        password: str = TEST_PASSWORD,
        is_active: bool = True,
    ) -> User:
        nonlocal counter
        counter += 1
        user = User(
            email=email or f"{role.value}{counter}@example.com",
            full_name=f"Test {role.value.title()} {counter}",
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        return user

    return _make_user


def login(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})
