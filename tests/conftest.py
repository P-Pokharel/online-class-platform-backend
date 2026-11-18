from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    ClassSession, Course, CourseSchedule, SessionStatus, Teacher, User, UserRole,
)

TEST_PASSWORD = "Password123"


class TestSettings(BaseSettings):
    """Test-only settings, read from the same .env but kept out of the app's Settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    test_database_url: str | None = None


def _test_database_url() -> str:
    """Return TEST_DATABASE_URL, refusing anything that could be the real database.

    The suite drops every table, so pointing it at the dev database would wipe it.
    """
    url = TestSettings().test_database_url
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


@pytest.fixture
def make_teacher(db: Session, make_user) -> Callable[..., Teacher]:
    def _make_teacher(title: str = "Lecturer", is_active: bool = True, **user_kwargs) -> Teacher:
        user = make_user(role=UserRole.TEACHER, is_active=is_active, **user_kwargs)
        teacher = Teacher(user=user, title=title)
        db.add(teacher)
        db.commit()
        return teacher

    return _make_teacher


@pytest.fixture
def admin_client(client: TestClient, make_user) -> TestClient:
    """The test client, logged in as an admin."""
    admin = make_user(role=UserRole.ADMIN)
    assert login(client, admin.email).status_code == 200
    return client


@pytest.fixture
def make_course(db: Session) -> Callable[..., Course]:
    """A course running from a month ago to three months ahead, published by default."""
    counter = 0

    def _make_course(
        teacher: Teacher,
        code: str | None = None,
        is_published: bool = True,
        schedules: list[tuple[int, time, str]] = (),  # (day_of_week, start_time, timezone)
        **fields,
    ) -> Course:
        nonlocal counter
        counter += 1
        today = date.today()
        course = Course(
            code=code or f"C{counter:03d}",
            title=fields.pop("title", f"Course {counter}"),
            teacher=teacher,
            is_published=is_published,
            starts_on=fields.pop("starts_on", today - timedelta(days=30)),
            ends_on=fields.pop("ends_on", today + timedelta(days=90)),
            schedules=[
                CourseSchedule(day_of_week=d, start_time=t, duration_minutes=60, timezone=tz)
                for d, t, tz in schedules
            ],
            **fields,
        )
        db.add(course)
        db.commit()
        return course

    return _make_course


@pytest.fixture
def make_session(db: Session) -> Callable[..., ClassSession]:
    def _make_session(
        course: Course,
        status: SessionStatus = SessionStatus.SCHEDULED,
        scheduled_for: datetime | None = None,
        title: str = "Class",
    ) -> ClassSession:
        session = ClassSession(course=course, status=status, scheduled_for=scheduled_for,
                               title=title)
        db.add(session)
        db.commit()
        return session

    return _make_session


def login_as(client: TestClient, user: User) -> TestClient:
    """Switch the client to `user`'s session (dropping any previous one)."""
    client.cookies.clear()
    assert login(client, user.email).status_code == 200
    return client
