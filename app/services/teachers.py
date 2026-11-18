from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password
from app.models import Course, Teacher, User, UserRole
from app.services.errors import ConflictError, NotFoundError, violated_constraint

USER_FIELDS = {"email", "full_name", "is_active"}
PROFILE_FIELDS = {"title", "department", "bio"}


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if violated_constraint(exc) == "uq_users_email":
            raise ConflictError("Email is already registered")
        raise


def create_teacher(db: Session, data: dict[str, Any]) -> Teacher:
    """Create the login account (role teacher) and the profile in one transaction."""
    user = User(
        email=data["email"],
        full_name=data["full_name"],
        hashed_password=hash_password(data["password"]),
        role=UserRole.TEACHER,
    )
    teacher = Teacher(
        user=user, title=data["title"], department=data.get("department"), bio=data.get("bio")
    )
    db.add(teacher)
    _commit(db)
    return teacher


def get_teacher(db: Session, teacher_id: int) -> Teacher:
    teacher = db.get(Teacher, teacher_id, options=[joinedload(Teacher.user)])
    if teacher is None:
        raise NotFoundError("Teacher not found")
    return teacher


def list_teachers(
    db: Session, search: str | None, page: int, page_size: int
) -> tuple[list[Teacher], int]:
    query = select(Teacher).join(Teacher.user)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    teachers = db.scalars(
        query.options(joinedload(Teacher.user))
        .order_by(User.full_name, Teacher.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(teachers), total


def update_teacher(db: Session, teacher_id: int, changes: dict[str, Any]) -> Teacher:
    teacher = get_teacher(db, teacher_id)
    for field in USER_FIELDS & changes.keys():
        setattr(teacher.user, field, changes[field])
    for field in PROFILE_FIELDS & changes.keys():
        setattr(teacher, field, changes[field])
    if "password" in changes:
        teacher.user.hashed_password = hash_password(changes["password"])
    _commit(db)
    return teacher


def delete_teacher(db: Session, teacher_id: int) -> None:
    """Delete the teacher's account and profile.

    Refused while they still teach courses: the courses would lose their teacher.
    Reassign or delete those courses first, or deactivate the teacher instead.
    """
    teacher = get_teacher(db, teacher_id)
    course_count = db.scalar(
        select(func.count()).select_from(Course).where(Course.teacher_id == teacher.id)
    )
    if course_count:
        raise ConflictError(
            f"Teacher still teaches {course_count} course(s); reassign or delete them first"
        )
    # Deleting the user removes the profile too (teachers.user_id is ON DELETE CASCADE).
    db.delete(teacher)
    db.delete(teacher.user)
    try:
        db.commit()
    except IntegrityError:
        # A course was assigned to this teacher between the check and the delete.
        db.rollback()
        raise ConflictError("Teacher still teaches courses; reassign or delete them first")
