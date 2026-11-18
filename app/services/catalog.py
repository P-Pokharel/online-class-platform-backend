from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import ClassSession, Course, Enrollment, EnrollmentStatus, SessionStatus, Teacher
from app.services.errors import NotFoundError
from app.services.timetable import earliest, next_slot_start

# Teacher name and timetable are needed for every course card; load them up front.
COURSE_LOAD = (selectinload(Course.schedules), joinedload(Course.teacher).joinedload(Teacher.user))

UPCOMING_SESSIONS_LIMIT = 10


@dataclass(frozen=True)
class CourseFacts:
    """Live figures about a course, computed at request time."""

    enrolled_count: int
    live_session_id: int | None
    next_class_at: datetime | None


def course_facts(db: Session, courses: Sequence[Course], now: datetime) -> dict[int, CourseFacts]:
    """Facts for many courses with three grouped queries, not three per course."""
    ids = [c.id for c in courses]
    if not ids:
        return {}
    enrolled = dict(db.execute(
        select(Enrollment.course_id, func.count())
        .where(Enrollment.course_id.in_(ids), Enrollment.status == EnrollmentStatus.ACTIVE)
        .group_by(Enrollment.course_id)
    ).all())
    live = dict(db.execute(
        select(ClassSession.course_id, ClassSession.id)
        .where(ClassSession.course_id.in_(ids), ClassSession.status == SessionStatus.LIVE)
    ).all())
    next_session = dict(db.execute(
        select(ClassSession.course_id, func.min(ClassSession.scheduled_for))
        .where(
            ClassSession.course_id.in_(ids),
            ClassSession.status == SessionStatus.SCHEDULED,
            ClassSession.scheduled_for > now,
        )
        .group_by(ClassSession.course_id)
    ).all())
    return {
        c.id: CourseFacts(
            enrolled_count=enrolled.get(c.id, 0),
            live_session_id=live.get(c.id),
            next_class_at=earliest(
                next_session.get(c.id),
                next_slot_start(c.schedules, c.starts_on, c.ends_on, now),
            ),
        )
        for c in courses
    }


def active_enrollment_course_ids(db: Session, student_id: int, course_ids: list[int]) -> set[int]:
    if not course_ids:
        return set()
    return set(db.scalars(
        select(Enrollment.course_id).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id.in_(course_ids),
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
    ))


def list_published_courses(
    db: Session, search: str | None, teacher_id: int | None, page: int, page_size: int
) -> tuple[list[Course], int]:
    query = select(Course).where(Course.is_published.is_(True))
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Course.code.ilike(pattern), Course.title.ilike(pattern)))
    if teacher_id is not None:
        query = query.where(Course.teacher_id == teacher_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    courses = db.scalars(
        query.options(*COURSE_LOAD)
        .order_by(Course.code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(courses), total


def get_published_course(db: Session, course_id: int) -> Course:
    """404 for unpublished courses too, so drafts look exactly like missing ones."""
    course = db.get(Course, course_id, options=COURSE_LOAD)
    if course is None or not course.is_published:
        raise NotFoundError("Course not found")
    return course


def upcoming_sessions(db: Session, course_id: int, now: datetime) -> list[ClassSession]:
    return list(db.scalars(
        select(ClassSession)
        .where(
            ClassSession.course_id == course_id,
            ClassSession.status == SessionStatus.SCHEDULED,
            ClassSession.scheduled_for > now,
        )
        .order_by(ClassSession.scheduled_for)
        .limit(UPCOMING_SESSIONS_LIMIT)
    ))
