from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings

app = FastAPI(title="Online Classes Platform")

# The Next.js app runs on another origin (port), so the browser asks permission
# before sending it API requests. allow_credentials lets it include our auth
# cookie. With credentials on, origins must be listed explicitly ("*" is refused
# by browsers), which also stops arbitrary sites from making cookie requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
