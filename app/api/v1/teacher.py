from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.deps import DbSession, TeacherUser
from app.schemas.courses import CourseStudent, TeacherCourse
from app.services import catalog, teaching

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/courses", response_model=list[TeacherCourse])
def my_teaching_courses(db: DbSession, user: TeacherUser) -> list[TeacherCourse]:
    """The courses the logged-in teacher teaches, including unpublished ones."""
    courses = teaching.teacher_courses(db, user.teacher)
    facts = catalog.course_facts(db, courses, datetime.now(UTC))
    return [TeacherCourse.build(c, facts[c.id]) for c in courses]


@router.get("/courses/{course_id}/students", response_model=list[CourseStudent])
def course_students(course_id: int, db: DbSession, user: TeacherUser) -> list[CourseStudent]:
    """Students actively enrolled in one of your courses. 403 for other teachers' courses."""
    return [CourseStudent.build(u, e) for u, e in teaching.course_students(db, user.teacher, course_id)]
