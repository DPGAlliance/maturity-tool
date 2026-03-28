from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import math
import time
from typing import Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.sql import func

from storage.models import (
    Branch,
    Commit,
    FetchLog,
    Issue,
    PullRequest,
    Release,
    Repo,
    Run,
)


def get_or_create_repo(session, owner: str, name: str, default_branch: str | None = None) -> Repo:
    repo = session.execute(
        select(Repo).where(Repo.owner == owner, Repo.name == name)
    ).scalar_one_or_none()
    if repo:
        if default_branch and repo.default_branch != default_branch:
            repo.default_branch = default_branch
            session.add(repo)
        return repo
    repo = Repo(owner=owner, name=name, default_branch=default_branch)
    session.add(repo)
    session.commit()
    return repo


def create_run(
    session,
    repo_id: int,
    source: str | None,
    notes: str | None = None,
) -> Run:
    run = Run(
        repo_id=repo_id,
        source=source,
        notes=notes,
    )
    session.add(run)
    session.commit()
    return run


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """Return a timezone-naive UTC datetime.

    We currently treat timezone as out-of-scope for cache freshness and only
    care about *days*. To avoid "offset-naive vs offset-aware" comparison
    errors across DB backends, we normalize timestamps to naive UTC for reads
    and writes.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def is_cache_fresh(session, repo_id: int, entity_type: str, max_age_days: int = 7) -> bool:
    fetch_log = session.execute(
        select(FetchLog).where(
            FetchLog.repo_id == repo_id,
            FetchLog.entity_type == entity_type,
        )
    ).scalar_one_or_none()
    if not fetch_log or not fetch_log.fetched_at:
        return False

    fetched_at = _to_naive_utc(fetch_log.fetched_at)
    if not fetched_at:
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    threshold = now - timedelta(days=max_age_days)
    return fetched_at >= threshold


def has_cache_entry(session, repo_id: int) -> bool:
    """Return True if this repo has any cached fetch timestamps."""
    return (
        session.execute(
            select(func.count(FetchLog.id)).where(FetchLog.repo_id == repo_id)
        ).scalar_one()
        > 0
    )


def get_last_fetch_at(session, repo_id: int) -> datetime | None:
    """Return the latest fetch timestamp across all entity types for a repo.

    Returned datetime is normalized to timezone-naive UTC for consistent display
    and comparisons.
    """
    latest = session.execute(
        select(func.max(FetchLog.fetched_at)).where(FetchLog.repo_id == repo_id)
    ).scalar_one_or_none()
    return _to_naive_utc(latest)


def record_fetch(session, repo_id: int, entity_type: str) -> None:
    fetch_log = session.execute(
        select(FetchLog).where(
            FetchLog.repo_id == repo_id,
            FetchLog.entity_type == entity_type,
        )
    ).scalar_one_or_none()

    # Store UTC-aware timestamps in the DB (models use timezone-aware columns),
    # but compare/display using timezone-naive UTC (see _to_naive_utc).
    now = datetime.now(timezone.utc)
    if fetch_log:
        fetch_log.fetched_at = now
        session.add(fetch_log)
    else:
        session.add(FetchLog(repo_id=repo_id, entity_type=entity_type, fetched_at=now))
    session.commit()


def _iter_batches(items: list[dict], batch_size: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def _format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _upsert_all(
    session,
    rows: Iterable,
    model,
    key_fields: tuple[str, ...],
    *,
    owner: str | None = None,
    repo: str | None = None,
    entity_type: str | None = None,
) -> None:
    rows = list(rows)
    if not rows:
        return

    seen = set()
    row_dicts = []
    columns = [col.name for col in model.__table__.columns if col.name != "id"]

    for row in rows:
        key = tuple(getattr(row, field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        row_dicts.append({col: getattr(row, col) for col in columns})

    if not row_dicts:
        return

    batch_size = 1000
    dialect = session.bind.dialect.name
    status_logger = logging.getLogger("refresh.status")
    total_rows = len(row_dicts)
    total_batches = math.ceil(total_rows / batch_size)
    log_batches = entity_type in {"commits", "issues", "prs"} and owner and repo

    for batch_index, batch in enumerate(_iter_batches(row_dicts, batch_size), start=1):
        if log_batches:
            status_logger.info(
                "owner=%s repo=%s stage=%s batch=%s/%s rows=%s total_rows=%s status=start",
                owner,
                repo,
                entity_type,
                batch_index,
                total_batches,
                len(batch),
                total_rows,
            )
            batch_start = time.monotonic()
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(model).values(batch)
            update_cols = {
                col: getattr(stmt.excluded, col)
                for col in columns
                if col not in key_fields
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=[getattr(model, field) for field in key_fields],
                set_=update_cols,
            )
            session.execute(stmt)
        else:
            session.execute(model.__table__.insert(), batch)

        if log_batches:
            status_logger.info(
                "owner=%s repo=%s stage=%s batch=%s/%s rows=%s total_rows=%s status=ok duration=%s",
                owner,
                repo,
                entity_type,
                batch_index,
                total_batches,
                len(batch),
                total_rows,
                _format_duration(time.monotonic() - batch_start),
            )

    session.commit()


def _clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        return value
    return value


def upsert_commits(
    session,
    repo_id: int,
    commits: Iterable[dict],
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> None:
    rows = [
        Commit(
            repo_id=repo_id,
            oid=_clean_value(item.get("oid")),
            authored_date=_clean_value(item.get("authoredDate")),
            author_login=_clean_value(item.get("author_login")),
            additions=_clean_value(item.get("additions")),
            deletions=_clean_value(item.get("deletions")),
            message=_clean_value(item.get("messageHeadline")),
        )
        for item in commits
    ]
    _upsert_all(
        session,
        rows,
        Commit,
        ("repo_id", "oid"),
        owner=owner,
        repo=repo,
        entity_type="commits",
    )


def upsert_branches(
    session,
    repo_id: int,
    branches: Iterable[dict],
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> None:
    rows = [
        Branch(
            repo_id=repo_id,
            name=_clean_value(item.get("branch_name")),
            last_commit_date=_clean_value(item.get("last_commit_date")),
            total_commits=_clean_value(item.get("total_commits")),
        )
        for item in branches
    ]
    _upsert_all(session, rows, Branch, ("repo_id", "name"))


def upsert_releases(
    session,
    repo_id: int,
    releases: Iterable[dict],
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> None:
    rows = [
        Release(
            repo_id=repo_id,
            tag_name=_clean_value(item.get("tag_name")),
            name=_clean_value(item.get("name")),
            created_at=_clean_value(item.get("created_at")),
            total_downloads=_clean_value(item.get("total_downloads")),
        )
        for item in releases
    ]
    _upsert_all(session, rows, Release, ("repo_id", "tag_name"))


def upsert_issues(
    session,
    repo_id: int,
    issues: Iterable[dict],
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> None:
    rows = [
        Issue(
            repo_id=repo_id,
            github_id=_clean_value(item.get("id")),
            created_at=_clean_value(item.get("createdAt")),
            closed_at=_clean_value(item.get("closedAt")),
            state=_clean_value(item.get("state")),
            author_login=_clean_value(item.get("author_login")),
            first_comment_created_at=_clean_value(item.get("first_comment_createdAt")),
            first_comment_author=_clean_value(item.get("first_comment_author")),
            labels=item.get("labels") or [],
        )
        for item in issues
    ]
    _upsert_all(
        session,
        rows,
        Issue,
        ("repo_id", "github_id"),
        owner=owner,
        repo=repo,
        entity_type="issues",
    )


def upsert_prs(
    session,
    repo_id: int,
    prs: Iterable[dict],
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> None:
    rows = [
        PullRequest(
            repo_id=repo_id,
            github_id=_clean_value(item.get("id")),
            created_at=_clean_value(item.get("createdAt")),
            merged_at=_clean_value(item.get("mergedAt")),
            closed_at=_clean_value(item.get("closedAt")),
            state=_clean_value(item.get("state")),
            author_login=_clean_value(item.get("author_login")),
            first_comment_created_at=_clean_value(item.get("first_comment_createdAt")),
            first_comment_author=_clean_value(item.get("first_comment_author")),
            labels=item.get("labels") or [],
        )
        for item in prs
    ]
    _upsert_all(
        session,
        rows,
        PullRequest,
        ("repo_id", "github_id"),
        owner=owner,
        repo=repo,
        entity_type="prs",
    )


def get_cached_commits(session, repo_id: int):
    return session.execute(select(Commit).where(Commit.repo_id == repo_id)).scalars().all()


def get_cached_branches(session, repo_id: int):
    return session.execute(
        select(Branch).where(Branch.repo_id == repo_id)
    ).scalars().all()


def get_cached_releases(session, repo_id: int):
    return session.execute(select(Release).where(Release.repo_id == repo_id)).scalars().all()


def get_cached_issues(session, repo_id: int):
    return session.execute(select(Issue).where(Issue.repo_id == repo_id)).scalars().all()


def get_cached_prs(session, repo_id: int):
    return session.execute(select(PullRequest).where(PullRequest.repo_id == repo_id)).scalars().all()
