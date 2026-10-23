"""Database engine, session factory and the FastAPI session dependency."""
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import settings

_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,                      # drop dead connections after a DB restart
    connect_args={"check_same_thread": False} if _is_sqlite else {"connect_timeout": 3},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


def get_db() -> Iterator[Session]:
    """One session per request; the caller commits, we always close (uncommitted work rolls back)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def db_ok() -> bool:
    """True if the database answers `SELECT 1` (used by /health)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def create_tables() -> None:
    """Create all tables (and the audit trigger) if they do not exist."""
    from app import models  # noqa: F401  (registers the models)

    Base.metadata.create_all(engine)
