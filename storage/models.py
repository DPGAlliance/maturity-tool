from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

try:
    from sqlalchemy import JSON
except ImportError:  # pragma: no cover
    JSON = None

Base = declarative_base()


def json_type():
    if JSON is not None:
        return JSON
    return JSONB


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    runs = relationship("Run", back_populates="repo", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="repo", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repo_owner_name"),)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    run_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    time_range: Mapped[str | None] = mapped_column(String(50))
    since_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    repo = relationship("Repo", back_populates="runs")
    metrics = relationship("Metric", back_populates="run", cascade="all, delete-orphan")


class FetchLog(Base):
    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("repo_id", "entity_type", name="uq_fetch_repo_entity"),)


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    oid: Mapped[str] = mapped_column(String(64), nullable=False)
    authored_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_login: Mapped[str | None] = mapped_column(String(200))
    additions: Mapped[int | None] = mapped_column(Integer)
    deletions: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("repo_id", "oid", name="uq_commit_repo_oid"),)


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    last_commit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_commits: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("repo_id", "name", name="uq_branch_repo_name"),)


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_downloads: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("repo_id", "tag_name", name="uq_release_repo_tag"),)


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    github_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str | None] = mapped_column(String(20))
    author_login: Mapped[str | None] = mapped_column(String(200))
    first_comment_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_comment_author: Mapped[str | None] = mapped_column(String(200))
    labels: Mapped[list | None] = mapped_column(json_type())

    __table_args__ = (UniqueConstraint("repo_id", "github_id", name="uq_issue_repo_id"),)


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    github_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str | None] = mapped_column(String(20))
    author_login: Mapped[str | None] = mapped_column(String(200))
    first_comment_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_comment_author: Mapped[str | None] = mapped_column(String(200))
    labels: Mapped[list | None] = mapped_column(json_type())

    __table_args__ = (UniqueConstraint("repo_id", "github_id", name="uq_pr_repo_id"),)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value_float: Mapped[float | None] = mapped_column(Float)
    value_int: Mapped[int | None] = mapped_column(Integer)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict | list | None] = mapped_column(json_type())

    run = relationship("Run", back_populates="metrics")

    __table_args__ = (UniqueConstraint("run_id", "scope", "name", name="uq_metric_run_scope_name"),)


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repos.id"))
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    summary_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | list | None] = mapped_column(json_type())

    repo = relationship("Repo", back_populates="summaries")
