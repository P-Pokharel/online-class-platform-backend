from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.core.deps import DbSession, OptionalUser, StudentUser
from app.models import Course, User, UserRole
from app.schemas.common import Page
from app.schemas.courses import CourseCard, CourseDetail, EnrollmentOut
from app.services import catalog
from app.services import enrollment as enrollment_service

router = APIRouter(prefix="/courses", tags=["courses"])


def _enrolled_ids(db: Session, user: User | None, courses: list[Course]) -> set[int] | None:
    """Course ids the user is actively enrolled in; None unless the user is a student."""
    if user is None or user.role != UserRole.STUDENT:
        return None
    return catalog.active_enrollment_course_ids(db, user.id, [c.id for c in courses])


@router.get("", response_model=Page[CourseCard])
def list_courses(
    db: DbSession,
    user: OptionalUser,
    search: Annotated[str | None, Query(max_length=100, description="Code or title")] = None,
    teacher_id: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CourseCard]:
    """Public catalog of published courses. Logging in as a student adds `is_enrolled`."""
    now = datetime.now(UTC)
    courses, total = catalog.list_published_courses(db, search, teacher_id, page, page_size)
    facts = catalog.course_facts(db, courses, now)
    enrolled = _enrolled_ids(db, user, courses)
    items = [
        CourseCard.build(c, facts[c.id], None if enrolled is None else c.id in enrolled)
        for c in courses
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{course_id}", response_model=CourseDetail)
def get_course(course_id: int, db: DbSession, user: OptionalUser) -> CourseDetail:
    """A published course. `live_session_id` is shown only to enrolled students and its teacher."""
    now = datetime.now(UTC)
    course = catalog.get_published_course(db, course_id)
    facts = catalog.course_facts(db, [course], now)[course.id]
    enrolled = _enrolled_ids(db, user, [course])
    is_enrolled = None if enrolled is None else course.id in enrolled
    teaches_it = user is not None and user.teacher is not None and user.teacher.id == course.teacher_id
    return CourseDetail.build_detail(
        course,
        facts,
        is_enrolled,
        upcoming=catalog.upcoming_sessions(db, course.id, now),
        can_join=bool(is_enrolled) or teaches_it,
    )


@router.post("/{course_id}/enroll", response_model=EnrollmentOut)
def enroll(course_id: int, db: DbSession, student: StudentUser) -> EnrollmentOut:
    """Enroll in a published course (free for now). 409 if already enrolled or the course has ended."""
    return EnrollmentOut.from_model(enrollment_service.enroll(db, student, course_id))


@router.post("/{course_id}/drop", response_model=EnrollmentOut)
def drop(course_id: int, db: DbSession, student: StudentUser) -> EnrollmentOut:
    """Drop a course. 409 if not currently enrolled. Enrolling again reactivates it."""
    return EnrollmentOut.from_model(enrollment_service.drop(db, student, course_id))
