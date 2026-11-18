from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, Enrollment, EnrollmentStatus, Teacher, User
from app.services.catalog import COURSE_LOAD
from app.services.errors import ForbiddenError, NotFoundError


def teacher_courses(db: Session, teacher: Teacher | None) -> list[Course]:
    """All courses the teacher teaches, published or not."""
    if teacher is None:  # a teacher account without a profile teaches nothing
        return []
    return list(db.scalars(
        select(Course).where(Course.teacher_id == teacher.id).options(*COURSE_LOAD)
        .order_by(Course.code)
    ))


def course_students(
    db: Session, teacher: Teacher | None, course_id: int
) -> list[tuple[User, Enrollment]]:
    """Actively enrolled students of a course the teacher teaches, sorted by name."""
    course = db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found")
    if teacher is None or course.teacher_id != teacher.id:
        raise ForbiddenError("You don't teach this course")
    rows = db.execute(
        select(User, Enrollment)
        .join(Enrollment, Enrollment.student_id == User.id)
        .where(Enrollment.course_id == course_id, Enrollment.status == EnrollmentStatus.ACTIVE)
        .order_by(User.full_name, User.id)
    ).all()
    return [(user, enrollment) for user, enrollment in rows]
