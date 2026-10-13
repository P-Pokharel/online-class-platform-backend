# Import every model here so Base.metadata knows about all tables
# (Alembic autogenerate relies on this).
from app.models.class_session import ClassSession, SessionAttendance
from app.models.course import Course, CourseSchedule
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentStatus, SessionStatus, UserRole
from app.models.teacher import Teacher
from app.models.user import User

__all__ = [
    "ClassSession",
    "Course",
    "CourseSchedule",
    "Enrollment",
    "EnrollmentStatus",
    "SessionAttendance",
    "SessionStatus",
    "Teacher",
    "User",
    "UserRole",
]
