import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import Base


def default_database_url() -> str:
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "maturity.db"))
    return f"sqlite:///{db_path}"


def get_engine(database_url: str | None = None):
    db_url = database_url or os.getenv("DATABASE_URL", default_database_url())
    if db_url.startswith("sqlite"):
        return create_engine(db_url, connect_args={"check_same_thread": False})
    return create_engine(db_url)


def get_session(database_url: str | None = None):
    engine = get_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def init_db(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
