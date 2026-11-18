from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import DbSession, require_admin
from app.schemas.admin import CourseCreate, CourseOut, CourseUpdate
from app.schemas.common import Page
from app.services import courses as course_service

router = APIRouter(
    prefix="/admin/courses", tags=["admin: courses"], dependencies=[Depends(require_admin)]
)


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(body: CourseCreate, db: DbSession) -> CourseOut:
    """Create a course with its weekly timetable. 409 if the code is taken."""
    return CourseOut.from_model(course_service.create_course(db, body.model_dump()))


@router.get("", response_model=Page[CourseOut])
def list_courses(
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100, description="Code or title")] = None,
    teacher_id: int | None = None,
    is_published: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CourseOut]:
    """All courses, including unpublished ones, sorted by code."""
    courses, total = course_service.list_courses(
        db, search, teacher_id, is_published, page, page_size
    )
    return Page(
        items=[CourseOut.from_model(c) for c in courses],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: DbSession) -> CourseOut:
    return CourseOut.from_model(course_service.get_course(db, course_id))


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(course_id: int, body: CourseUpdate, db: DbSession) -> CourseOut:
    """Change only the fields sent. `schedules`, when sent, replaces the whole timetable."""
    changes = body.model_dump(exclude_unset=True)
    return CourseOut.from_model(course_service.update_course(db, course_id, changes))


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: int, db: DbSession) -> None:
    """Delete a course. 409 once it has enrollments or class sessions: unpublish instead."""
    course_service.delete_course(db, course_id)
