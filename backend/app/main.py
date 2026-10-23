"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import create_tables, db_ok
from app.errors import register_error_handlers
from app.events import publisher
from app.routers import applications, audit, auth, branch, config, dashboard, documents, review
from app.settings import settings

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("onboardiq")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.jwt_secret:
        log.warning("JWT_SECRET is not set; login will not work until it is configured")
    create_tables()
    yield
    publisher.flush()                            # send any queued events before shutdown


app = FastAPI(
    title="OnboardIQ API",
    version="1.0.0",
    description="KYC onboarding: document extraction, rules R1–R17, screening, maker-checker, audit.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

api = APIRouter(prefix="/api/v1")


@api.get("/health", tags=["system"])
def health() -> dict:
    """Liveness plus a quick view of dependencies."""
    return {
        "status": "ok",
        "db": "up" if db_ok() else "down",
        "kafka": "enabled" if publisher.enabled else "disabled",
        "extraction_provider": settings.extraction_provider,
    }


for module in (auth, applications, branch, documents, review, dashboard, audit, config):
    api.include_router(module.router)
app.include_router(api)
