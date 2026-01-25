from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from api.deps import get_db_session, require_api_key
from api.schemas import SummaryOut
from storage.models import Repo, Summary


router = APIRouter(tags=["summaries"], dependencies=[Depends(require_api_key)])


def _repo_lookup(session, owner: str, repo: str) -> Repo:
    repo_obj = session.execute(
        select(Repo).where(Repo.owner == owner, Repo.name == repo)
    ).scalar_one_or_none()
    if not repo_obj:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo_obj


@router.get("/repos/{owner}/{repo}/summary", response_model=SummaryOut)
def get_repo_summary(owner: str, repo: str, session=Depends(get_db_session)):
    repo_obj = _repo_lookup(session, owner, repo)
    summary = (
        session.execute(
            select(Summary)
            .where(Summary.repo_id == repo_obj.id, Summary.summary_scope == "repo")
            .order_by(Summary.created_at.desc())
        )
        .scalars()
        .first()
    )
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return SummaryOut(
        id=summary.id,
        owner=summary.owner,
        repo=repo_obj.name,
        summary_scope=summary.summary_scope,
        run_id=summary.run_id,
        created_at=summary.created_at,
        model=summary.model,
        prompt_version=summary.prompt_version,
        summary_text=summary.summary_text,
        metadata_json=summary.metadata_json,
    )


@router.get("/repos/{owner}/{repo}/summaries", response_model=List[SummaryOut])
def list_repo_summaries(
    owner: str,
    repo: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session=Depends(get_db_session),
):
    repo_obj = _repo_lookup(session, owner, repo)
    summaries = (
        session.execute(
            select(Summary)
            .where(Summary.repo_id == repo_obj.id, Summary.summary_scope == "repo")
            .order_by(Summary.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        SummaryOut(
            id=summary.id,
            owner=summary.owner,
            repo=repo_obj.name,
            summary_scope=summary.summary_scope,
            run_id=summary.run_id,
            created_at=summary.created_at,
            model=summary.model,
            prompt_version=summary.prompt_version,
            summary_text=summary.summary_text,
            metadata_json=summary.metadata_json,
        )
        for summary in summaries
    ]


@router.get("/orgs/{owner}/summary", response_model=SummaryOut)
def get_org_summary(owner: str, session=Depends(get_db_session)):
    summary = (
        session.execute(
            select(Summary)
            .where(Summary.owner == owner, Summary.summary_scope == "org")
            .order_by(Summary.created_at.desc())
        )
        .scalars()
        .first()
    )
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return SummaryOut(
        id=summary.id,
        owner=summary.owner,
        repo=None,
        summary_scope=summary.summary_scope,
        run_id=summary.run_id,
        created_at=summary.created_at,
        model=summary.model,
        prompt_version=summary.prompt_version,
        summary_text=summary.summary_text,
        metadata_json=summary.metadata_json,
    )


@router.get("/orgs/{owner}/summaries", response_model=List[SummaryOut])
def list_org_summaries(
    owner: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session=Depends(get_db_session),
):
    summaries = (
        session.execute(
            select(Summary)
            .where(Summary.owner == owner, Summary.summary_scope == "org")
            .order_by(Summary.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        SummaryOut(
            id=summary.id,
            owner=summary.owner,
            repo=None,
            summary_scope=summary.summary_scope,
            run_id=summary.run_id,
            created_at=summary.created_at,
            model=summary.model,
            prompt_version=summary.prompt_version,
            summary_text=summary.summary_text,
            metadata_json=summary.metadata_json,
        )
        for summary in summaries
    ]
