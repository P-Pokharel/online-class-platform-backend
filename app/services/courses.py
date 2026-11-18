from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import ClassSession, Course, CourseSchedule, Enrollment, Teacher
from app.services.errors import (
    ConflictError, InvalidReferenceError, NotFoundError, ValidationError, violated_constraint,
)

SIMPLE_FIELDS = {
    "code", "title", "description", "price_cents", "starts_on", "ends_on", "is_published",
}

# Load the teacher (with their name) and the timetable together with the course,
# so building the response doesn't issue one extra query per course.
_LOAD = (selectinload(Course.schedules), joinedload(Course.teacher).joinedload(Teacher.user))


def _usable_teacher(db: Session, teacher_id: int) -> Teacher:
    teacher = db.get(Teacher, teacher_id, options=[joinedload(Teacher.user)])
    if teacher is None:
        raise InvalidReferenceError(f"Teacher {teacher_id} does not exist")
    if not teacher.user.is_active:
        raise InvalidReferenceError(f"Teacher {teacher_id} is deactivated")
    return teacher


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if violated_constraint(exc) == "uq_courses_code":
            raise ConflictError("A course with this code already exists")
        raise


def create_course(db: Session, data: dict[str, Any]) -> Course:
    course = Course(
        **{field: data[field] for field in SIMPLE_FIELDS if field in data},
        teacher=_usable_teacher(db, data["teacher_id"]),
        schedules=[CourseSchedule(**slot) for slot in data.get("schedules", [])],
    )
    db.add(course)
    _commit(db)
    return get_course(db, course.id)


def get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id, options=_LOAD, populate_existing=True)
    if course is None:
        raise NotFoundError("Course not found")
    return course


def list_courses(
    db: Session,
    search: str | None,
    teacher_id: int | None,
    is_published: bool | None,
    page: int,
    page_size: int,
) -> tuple[list[Course], int]:
    query = select(Course)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Course.code.ilike(pattern), Course.title.ilike(pattern)))
    if teacher_id is not None:
        query = query.where(Course.teacher_id == teacher_id)
    if is_published is not None:
        query = query.where(Course.is_published == is_published)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    courses = db.scalars(
        query.options(*_LOAD)
        .order_by(Course.code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(courses), total


def update_course(db: Session, course_id: int, changes: dict[str, Any]) -> Course:
    course = get_course(db, course_id)
    for field in SIMPLE_FIELDS & changes.keys():
        setattr(course, field, changes[field])
    # Dates may change one at a time, so compare the combined result.
    if course.ends_on < course.starts_on:
        raise ValidationError("ends_on must not be before starts_on")
    if "teacher_id" in changes:
        course.teacher = _usable_teacher(db, changes["teacher_id"])
    if "schedules" in changes:
        # delete-orphan cascade on Course.schedules removes the old rows.
        course.schedules = [CourseSchedule(**slot) for slot in changes["schedules"]]
    _commit(db)
    return get_course(db, course.id)


def delete_course(db: Session, course_id: int) -> None:
    """Delete a course and its timetable.

    Refused once students have enrolled or classes have been held, so enrollment
    and attendance history is never lost. Unpublish the course instead.
    """
    course = get_course(db, course_id)
    has_history = db.scalar(
        select(
            exists().where(Enrollment.course_id == course.id)
            | exists().where(ClassSession.course_id == course.id)
        )
    )
    if has_history:
        raise ConflictError(
            "Course has enrollments or class sessions; unpublish it instead of deleting"
        )
    db.delete(course)
    try:
        db.commit()
    except IntegrityError:
        # Someone enrolled between the check and the delete.
        db.rollback()
        raise ConflictError(
            "Course has enrollments or class sessions; unpublish it instead of deleting"
        )
