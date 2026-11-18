"""Enrolling and dropping.

Kept separate from the routes on purpose: the payment phase (plan Phase 10) will
call enroll() only after a payment succeeds, without rewriting it.
"""
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import Course, Enrollment, EnrollmentStatus, Teacher, User
from app.services.catalog import get_published_course
from app.services.errors import ConflictError, NotFoundError


def _find(db: Session, student: User, course_id: int) -> Enrollment | None:
    return db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id, Enrollment.course_id == course_id
        )
    )


def enroll(db: Session, student: User, course_id: int, today: date | None = None) -> Enrollment:
    """Make `student` an active member of a published course.

    There is one enrollment row per (student, course): re-enrolling after a drop
    reactivates that row instead of creating another.
    """
    course = get_published_course(db, course_id)
    if course.ends_on < (today or date.today()):
        raise ConflictError("Course has already ended")

    enrollment = _find(db, student, course.id)
    if enrollment is not None and enrollment.status == EnrollmentStatus.ACTIVE:
        raise ConflictError("Already enrolled in this course")
    if enrollment is None:
        enrollment = Enrollment(student_id=student.id, course_id=course.id)
        db.add(enrollment)
    else:
        enrollment.status = EnrollmentStatus.ACTIVE
        enrollment.enrolled_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError:
        # A second enroll request for the same pair won the race.
        db.rollback()
        raise ConflictError("Already enrolled in this course")
    db.refresh(enrollment)  # load the database-set enrolled_at
    return enrollment


def drop(db: Session, student: User, course_id: int) -> Enrollment:
    """Set the student's enrollment to dropped. The row stays, so history is kept."""
    if db.get(Course, course_id) is None:
        raise NotFoundError("Course not found")
    enrollment = _find(db, student, course_id)
    if enrollment is None or enrollment.status != EnrollmentStatus.ACTIVE:
        raise ConflictError("Not enrolled in this course")
    enrollment.status = EnrollmentStatus.DROPPED
    db.commit()
    return enrollment


def my_enrollments(db: Session, student: User) -> list[Enrollment]:
    """The student's active enrollments, each with its course, teacher and timetable loaded."""
    course = joinedload(Enrollment.course)
    return list(db.scalars(
        select(Enrollment)
        .join(Enrollment.course)
        .where(Enrollment.student_id == student.id, Enrollment.status == EnrollmentStatus.ACTIVE)
        .options(
            course.joinedload(Course.teacher).joinedload(Teacher.user),
            course.selectinload(Course.schedules),
        )
        .order_by(Course.code)
    ).unique())
