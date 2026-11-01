import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base for EvidenceAI persistence models."""


def _database_url() -> str:
    return os.getenv(
        "EVIDENCE_AI_DATABASE_URL",
        "postgresql+psycopg://evidence_ai:evidence_ai_dev@localhost:5432/evidence_ai",
    )


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
