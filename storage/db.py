import os

from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import sessionmaker

from storage.models import Base
from storage.secrets import get_secret


def build_database_url() -> str:
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = get_secret("DB_PASSWORD")

    if not all([host, port, name, user, password]):
        raise RuntimeError(
            "Database config is required. Set DB_HOST, DB_PORT, DB_NAME, DB_USER, and DB_PASSWORD or DB_PASSWORD_FILE."
        )

    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=name,
    ).render_as_string(hide_password=False)


def get_engine(database_url: str | None = None):
    db_url = database_url or build_database_url()
    return create_engine(db_url)


def get_session(database_url: str | None = None):
    engine = get_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def init_db(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    # create_all() does not add columns to tables created by older releases.
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE repo_scan_jobs
                ADD COLUMN IF NOT EXISTS stage VARCHAR(50),
                ADD COLUMN IF NOT EXISTS summary_status VARCHAR(20),
                ADD COLUMN IF NOT EXISTS summary_error_message TEXT,
                ADD COLUMN IF NOT EXISTS summary_finished_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP WITH TIME ZONE
                """
            )
        )
