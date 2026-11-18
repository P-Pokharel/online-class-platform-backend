from fastapi import APIRouter

from app.api.v1 import admin_courses, admin_teachers, auth, courses, me, teacher

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin_teachers.router)
api_router.include_router(admin_courses.router)
api_router.include_router(courses.router)
api_router.include_router(teacher.router)
api_router.include_router(me.router)


@api_router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
