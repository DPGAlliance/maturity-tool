import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base


def get_engine(database_url: str | None = None):
    db_url = database_url or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required (Postgres only)")
    return create_engine(db_url)


def get_session(database_url: str | None = None):
    engine = get_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def init_db(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
