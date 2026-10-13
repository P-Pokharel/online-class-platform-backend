from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SessionStatus, string_enum

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User


class ClassSession(Base):

    __tablename__ = "class_sessions"
    __table_args__ = (
        Index(
            "uq_class_sessions_one_live_per_course",
            "course_id",
            unique=True,
            postgresql_where=text("status = 'live'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    started_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[SessionStatus] = mapped_column(
        string_enum(SessionStatus),
        default=SessionStatus.SCHEDULED,
        server_default=SessionStatus.SCHEDULED.value,
    )
    janus_room_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped["Course"] = relationship(back_populates="sessions")
    started_by: Mapped["User | None"] = relationship()
    attendance: Mapped[list["SessionAttendance"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionAttendance(Base):

    __tablename__ = "session_attendance"
    __table_args__ = (Index(None, "session_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped["ClassSession"] = relationship(back_populates="attendance")
    user: Mapped["User"] = relationship()
