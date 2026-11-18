from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.deps import DbSession, StudentUser
from app.schemas.courses import MyCourse
from app.services import catalog
from app.services import enrollment as enrollment_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/courses", response_model=list[MyCourse])
def my_courses(db: DbSession, student: StudentUser) -> list[MyCourse]:
    """The student's enrolled courses, with next class time and the live session to join."""
    enrollments = enrollment_service.my_enrollments(db, student)
    facts = catalog.course_facts(db, [e.course for e in enrollments], datetime.now(UTC))
    return [MyCourse.build_mine(e, facts[e.course_id]) for e in enrollments]
