from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import DbSession, require_admin
from app.schemas.admin import TeacherCreate, TeacherOut, TeacherUpdate
from app.schemas.common import Page
from app.services import teachers as teacher_service

router = APIRouter(
    prefix="/admin/teachers", tags=["admin: teachers"], dependencies=[Depends(require_admin)]
)


@router.post("", response_model=TeacherOut, status_code=status.HTTP_201_CREATED)
def create_teacher(body: TeacherCreate, db: DbSession) -> TeacherOut:
    """Create a teacher's login account and profile. 409 if the email is taken."""
    return TeacherOut.from_model(teacher_service.create_teacher(db, body.model_dump()))


@router.get("", response_model=Page[TeacherOut])
def list_teachers(
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100, description="Name or email")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[TeacherOut]:
    """All teachers, including deactivated ones, sorted by name."""
    teachers, total = teacher_service.list_teachers(db, search, page, page_size)
    return Page(
        items=[TeacherOut.from_model(t) for t in teachers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: DbSession) -> TeacherOut:
    return TeacherOut.from_model(teacher_service.get_teacher(db, teacher_id))


@router.patch("/{teacher_id}", response_model=TeacherOut)
def update_teacher(teacher_id: int, body: TeacherUpdate, db: DbSession) -> TeacherOut:
    """Change only the fields sent. `is_active: false` deactivates; `password` resets it."""
    changes = body.model_dump(exclude_unset=True)
    return TeacherOut.from_model(teacher_service.update_teacher(db, teacher_id, changes))


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher(teacher_id: int, db: DbSession) -> None:
    """Delete the teacher and their account. 409 while they still teach any course."""
    teacher_service.delete_teacher(db, teacher_id)
