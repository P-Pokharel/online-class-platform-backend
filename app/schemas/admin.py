import re
from datetime import date, datetime, time
from typing import Annotated, Self
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from app.models import Course, CourseSchedule, Teacher
from app.schemas.auth import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, NormalizedEmail
from app.schemas.common import ScheduleOut, TeacherSummary

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Department = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]
_COURSE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,19}$")


def _course_code(value: str) -> str:
    value = value.strip().upper()
    if not _COURSE_CODE.fullmatch(value):
        raise ValueError("must be 2-20 letters, digits or dashes, e.g. 'CS101'")
    return value


CourseCode = Annotated[str, AfterValidator(_course_code)]
CourseTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PriceCents = Annotated[int, Field(ge=0, le=10_000_000)]

_TIMEZONES = available_timezones()


def _known_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("must be an IANA timezone name, e.g. 'Asia/Kathmandu'")
    return value


# --- teachers ------------------------------------------------------------------


class TeacherCreate(BaseModel):
    email: NormalizedEmail
    full_name: Name
    password: Password
    title: Title
    department: Department | None = None
    bio: str | None = Field(default=None, max_length=5000)


class TeacherUpdate(BaseModel):
    email: NormalizedEmail = None
    full_name: Name = None
    password: Password = None  
    title: Title = None
    department: Department | None = None
    bio: str | None = Field(default=None, max_length=5000)
    is_active: bool = None


class TeacherOut(BaseModel):
    id: int
    user_id: int
    email: str
    full_name: str
    is_active: bool
    title: str
    department: str | None
    bio: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, teacher: Teacher) -> Self:
        return cls(
            id=teacher.id,
            user_id=teacher.user_id,
            email=teacher.user.email,
            full_name=teacher.user.full_name,
            is_active=teacher.user.is_active,
            title=teacher.title,
            department=teacher.department,
            bio=teacher.bio,
            created_at=teacher.created_at,
        )


# --- courses -------------------------------------------------------------------


class ScheduleIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0 = Monday … 6 = Sunday")
    start_time: time = Field(description="Local wall-clock time in `timezone`")
    duration_minutes: int = Field(gt=0, le=600)
    timezone: Annotated[str, AfterValidator(_known_timezone)]


class CourseCreate(BaseModel):
    code: CourseCode
    title: CourseTitle
    description: str = Field(default="", max_length=10_000)
    teacher_id: int
    price_cents: PriceCents = 0
    starts_on: date
    ends_on: date
    is_published: bool = False
    schedules: list[ScheduleIn] = Field(default_factory=list, max_length=14)

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class CourseUpdate(BaseModel):
    code: CourseCode = None
    title: CourseTitle = None
    description: str = Field(default=None, max_length=10_000)
    teacher_id: int = None
    price_cents: PriceCents = None
    starts_on: date = None
    ends_on: date = None
    is_published: bool = None
    # When given, replaces the course's whole weekly timetable.
    schedules: list[ScheduleIn] = Field(default=None, max_length=14)


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    description: str
    price_cents: int
    starts_on: date
    ends_on: date
    is_published: bool
    created_at: datetime
    teacher: TeacherSummary
    schedules: list[ScheduleOut]

    @classmethod
    def from_model(cls, course: Course) -> Self:
        schedules: list[CourseSchedule] = sorted(
            course.schedules, key=lambda s: (s.day_of_week, s.start_time)
        )
        return cls(
            id=course.id,
            code=course.code,
            title=course.title,
            description=course.description,
            price_cents=course.price_cents,
            starts_on=course.starts_on,
            ends_on=course.ends_on,
            is_published=course.is_published,
            created_at=course.created_at,
            teacher=TeacherSummary(
                id=course.teacher.id,
                full_name=course.teacher.user.full_name,
                title=course.teacher.title,
            ),
            schedules=[ScheduleOut.model_validate(s) for s in schedules],
        )
