from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.services.errors import (
    ConflictError, ForbiddenError, InvalidReferenceError, NotFoundError, ServiceError,
    ValidationError,
)

app = FastAPI(title="Online Classes Platform")

SERVICE_ERROR_STATUS = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidReferenceError: status.HTTP_400_BAD_REQUEST,
    ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@app.exception_handler(ServiceError)
def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=SERVICE_ERROR_STATUS[type(exc)], content={"detail": exc.detail})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
