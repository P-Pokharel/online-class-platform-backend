from datetime import time
from typing import Self

from pydantic import BaseModel, ConfigDict

from app.models import CourseSchedule, Teacher


class Page[T](BaseModel):
    """One page of a list endpoint."""

    items: list[T]
    total: int
    page: int
    page_size: int


class ScheduleOut(BaseModel):
    """One weekly slot. `start_time` is wall-clock time in `timezone`."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    day_of_week: int
    start_time: time
    duration_minutes: int
    timezone: str

    @classmethod
    def list_from(cls, schedules: list[CourseSchedule]) -> list[Self]:
        ordered = sorted(schedules, key=lambda s: (s.day_of_week, s.start_time))
        return [cls.model_validate(s) for s in ordered]


class TeacherSummary(BaseModel):
    id: int
    full_name: str
    title: str

    @classmethod
    def from_model(cls, teacher: Teacher) -> Self:
        return cls(id=teacher.id, full_name=teacher.user.full_name, title=teacher.title)
