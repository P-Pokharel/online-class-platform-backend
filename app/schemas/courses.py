from datetime import date, datetime
from typing import Self

from pydantic import BaseModel

from app.models import ClassSession, Course, Enrollment, EnrollmentStatus, SessionStatus, User
from app.schemas.common import ScheduleOut, TeacherSummary
from app.services.catalog import CourseFacts

SHORT_DESCRIPTION_LENGTH = 200


def short_description(text: str, limit: int = SHORT_DESCRIPTION_LENGTH) -> str:
    """The first `limit` characters, cut at a word boundary."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


class CourseCard(BaseModel):
    """A course in the public catalog."""

    id: int
    code: str
    title: str
    short_description: str
    price_cents: int
    teacher: TeacherSummary
    starts_on: date
    ends_on: date
    schedules: list[ScheduleOut]
    # Next upcoming scheduled session or weekly slot, whichever comes first (UTC).
    next_class_at: datetime | None
    enrolled_count: int
    is_live: bool
    # Only for a logged-in student; null for anonymous visitors and other roles.
    is_enrolled: bool | None

    @classmethod
    def build(cls, course: Course, facts: CourseFacts, is_enrolled: bool | None) -> Self:
        return cls(
            id=course.id,
            code=course.code,
            title=course.title,
            short_description=short_description(course.description),
            price_cents=course.price_cents,
            teacher=TeacherSummary.from_model(course.teacher),
            starts_on=course.starts_on,
            ends_on=course.ends_on,
            schedules=ScheduleOut.list_from(course.schedules),
            next_class_at=facts.next_class_at,
            enrolled_count=facts.enrolled_count,
            is_live=facts.live_session_id is not None,
            is_enrolled=is_enrolled,
        )


class TeacherProfile(TeacherSummary):
    department: str | None
    bio: str | None


class SessionSummary(BaseModel):
    id: int
    title: str
    status: SessionStatus
    scheduled_for: datetime | None

    @classmethod
    def from_model(cls, session: ClassSession) -> Self:
        return cls(id=session.id, title=session.title, status=session.status,
                   scheduled_for=session.scheduled_for)


class CourseDetail(CourseCard):
    """Everything on the card, plus the full description and timetable details."""

    description: str
    teacher: TeacherProfile
    upcoming_sessions: list[SessionSummary]
    # Only for an enrolled student or the course's teacher; null for everyone else.
    live_session_id: int | None

    @classmethod
    def build_detail(
        cls,
        course: Course,
        facts: CourseFacts,
        is_enrolled: bool | None,
        upcoming: list[ClassSession],
        can_join: bool,
    ) -> Self:
        card = CourseCard.build(course, facts, is_enrolled).model_dump()
        teacher = course.teacher
        card["teacher"] = TeacherProfile(
            id=teacher.id, full_name=teacher.user.full_name, title=teacher.title,
            department=teacher.department, bio=teacher.bio,
        )
        return cls(
            **card,
            description=course.description,
            upcoming_sessions=[SessionSummary.from_model(s) for s in upcoming],
            live_session_id=facts.live_session_id if can_join else None,
        )


class TeacherCourse(BaseModel):
    """A course in the teacher's own list (published or not)."""

    id: int
    code: str
    title: str
    is_published: bool
    starts_on: date
    ends_on: date
    schedules: list[ScheduleOut]
    enrolled_count: int
    next_class_at: datetime | None
    is_live: bool
    live_session_id: int | None

    @classmethod
    def build(cls, course: Course, facts: CourseFacts) -> Self:
        return cls(
            id=course.id,
            code=course.code,
            title=course.title,
            is_published=course.is_published,
            starts_on=course.starts_on,
            ends_on=course.ends_on,
            schedules=ScheduleOut.list_from(course.schedules),
            enrolled_count=facts.enrolled_count,
            next_class_at=facts.next_class_at,
            is_live=facts.live_session_id is not None,
            live_session_id=facts.live_session_id,
        )


class CourseStudent(BaseModel):
    id: int
    full_name: str
    email: str
    enrolled_at: datetime

    @classmethod
    def build(cls, user: User, enrollment: Enrollment) -> Self:
        return cls(id=user.id, full_name=user.full_name, email=user.email,
                   enrolled_at=enrollment.enrolled_at)


class EnrollmentOut(BaseModel):
    course_id: int
    status: EnrollmentStatus
    enrolled_at: datetime

    @classmethod
    def from_model(cls, enrollment: Enrollment) -> Self:
        return cls(course_id=enrollment.course_id, status=enrollment.status,
                   enrolled_at=enrollment.enrolled_at)


class MyCourse(CourseCard):
    """A course the student is enrolled in, with what they need to join a live class."""

    enrolled_at: datetime
    live_session_id: int | None

    @classmethod
    def build_mine(cls, enrollment: Enrollment, facts: CourseFacts) -> Self:
        card = CourseCard.build(enrollment.course, facts, is_enrolled=True).model_dump()
        return cls(**card, enrolled_at=enrollment.enrolled_at,
                   live_session_id=facts.live_session_id)
