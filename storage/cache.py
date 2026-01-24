from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd
from sqlalchemy import select

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
    time_range: str | None,
    since_date: datetime | None,
    source: str | None,
    notes: str | None = None,
) -> Run:
    run = Run(
        repo_id=repo_id,
        time_range=time_range,
        since_date=since_date,
        source=source,
        notes=notes,
    )
    session.add(run)
    session.commit()
    return run


def is_cache_fresh(session, repo_id: int, entity_type: str, max_age_days: int = 7) -> bool:
    fetch_log = session.execute(
        select(FetchLog).where(
            FetchLog.repo_id == repo_id,
            FetchLog.entity_type == entity_type,
        )
    ).scalar_one_or_none()
    if not fetch_log:
        return False
    threshold = datetime.utcnow() - timedelta(days=max_age_days)
    return fetch_log.fetched_at >= threshold


def record_fetch(session, repo_id: int, entity_type: str) -> None:
    fetch_log = session.execute(
        select(FetchLog).where(
            FetchLog.repo_id == repo_id,
            FetchLog.entity_type == entity_type,
        )
    ).scalar_one_or_none()
    if fetch_log:
        fetch_log.fetched_at = datetime.utcnow()
        session.add(fetch_log)
    else:
        session.add(FetchLog(repo_id=repo_id, entity_type=entity_type))
    session.commit()


def _upsert_all(session, rows: Iterable, model, key_fields: tuple[str, ...]) -> None:
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

    dialect = session.bind.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(model).values(row_dicts)
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
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(model).values(row_dicts)
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
        session.execute(model.__table__.insert(), row_dicts)

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


def upsert_commits(session, repo_id: int, commits: Iterable[dict]) -> None:
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
    _upsert_all(session, rows, Commit, ("repo_id", "oid"))


def upsert_branches(session, repo_id: int, branches: Iterable[dict]) -> None:
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


def upsert_releases(session, repo_id: int, releases: Iterable[dict]) -> None:
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


def upsert_issues(session, repo_id: int, issues: Iterable[dict]) -> None:
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
    _upsert_all(session, rows, Issue, ("repo_id", "github_id"))


def upsert_prs(session, repo_id: int, prs: Iterable[dict]) -> None:
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
    _upsert_all(session, rows, PullRequest, ("repo_id", "github_id"))


def get_cached_commits(session, repo_id: int, since_date=None):
    query = select(Commit).where(Commit.repo_id == repo_id)
    if since_date is not None:
        query = query.where(Commit.authored_date >= since_date)
    return session.execute(query).scalars().all()


def get_cached_branches(session, repo_id: int):
    return session.execute(
        select(Branch).where(Branch.repo_id == repo_id)
    ).scalars().all()


def get_cached_releases(session, repo_id: int, since_date=None):
    query = select(Release).where(Release.repo_id == repo_id)
    if since_date is not None:
        query = query.where(Release.created_at >= since_date)
    return session.execute(query).scalars().all()


def get_cached_issues(session, repo_id: int, since_date=None):
    query = select(Issue).where(Issue.repo_id == repo_id)
    if since_date is not None:
        query = query.where(Issue.created_at >= since_date)
    return session.execute(query).scalars().all()


def get_cached_prs(session, repo_id: int, since_date=None):
    query = select(PullRequest).where(PullRequest.repo_id == repo_id)
    if since_date is not None:
        query = query.where(PullRequest.created_at >= since_date)
    return session.execute(query).scalars().all()
