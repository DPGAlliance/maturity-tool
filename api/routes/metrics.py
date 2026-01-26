from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from api.deps import get_db_session, require_api_key
from api.schemas import MetricsHistoryOut, MetricsOut, RunOut
from storage.models import Metric, Repo, Run


router = APIRouter(tags=["metrics"], dependencies=[Depends(require_api_key)])


def _metric_value(metric: Metric):
    if metric.value_int is not None:
        return metric.value_int
    if metric.value_float is not None:
        return metric.value_float
    if metric.value_text is not None:
        return metric.value_text
    if metric.value_json is not None:
        return metric.value_json
    return None


def _metrics_by_scope(metrics: List[Metric]) -> Dict[str, Dict[str, object]]:
    scoped: Dict[str, Dict[str, object]] = {}
    for metric in metrics:
        scoped.setdefault(metric.scope, {})[metric.name] = _metric_value(metric)
    return scoped


def _get_repo(session, owner: str, repo: str) -> Repo:
    repo_obj = session.execute(
        select(Repo).where(Repo.owner == owner, Repo.name == repo)
    ).scalar_one_or_none()
    if not repo_obj:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo_obj


def _get_latest_run(session, repo_id: int) -> Optional[Run]:
    return session.execute(
        select(Run).where(Run.repo_id == repo_id).order_by(Run.run_started_at.desc())
    ).scalars().first()


@router.get("/repos/{owner}/{repo}/metrics", response_model=MetricsOut)
def get_repo_metrics(
    owner: str,
    repo: str,
    run_id: Optional[int] = None,
    session=Depends(get_db_session),
):
    repo_obj = _get_repo(session, owner, repo)
    if run_id is not None:
        run = session.execute(
            select(Run).where(Run.repo_id == repo_obj.id, Run.id == run_id)
        ).scalar_one_or_none()
    else:
        run = _get_latest_run(session, repo_obj.id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    metrics = session.execute(select(Metric).where(Metric.run_id == run.id)).scalars().all()
    return MetricsOut(
        owner=repo_obj.owner,
        repo=repo_obj.name,
        run=RunOut(
            id=run.id,
            run_started_at=run.run_started_at,
            time_range=run.time_range,
            since_date=run.since_date,
        ),
        metrics=_metrics_by_scope(metrics),
    )


@router.get("/repos/{owner}/{repo}/metrics/history", response_model=MetricsHistoryOut)
def get_repo_metrics_history(
    owner: str,
    repo: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session=Depends(get_db_session),
):
    repo_obj = _get_repo(session, owner, repo)
    runs = (
        session.execute(
            select(Run)
            .where(Run.repo_id == repo_obj.id)
            .order_by(Run.run_started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    metrics_by_run = {}
    if runs:
        run_ids = [run.id for run in runs]
        metrics = session.execute(select(Metric).where(Metric.run_id.in_(run_ids))).scalars().all()
        for metric in metrics:
            metrics_by_run.setdefault(metric.run_id, []).append(metric)

    results = []
    for run in runs:
        results.append(
            MetricsOut(
                owner=repo_obj.owner,
                repo=repo_obj.name,
                run=RunOut(
                    id=run.id,
                    run_started_at=run.run_started_at,
                    time_range=run.time_range,
                    since_date=run.since_date,
                ),
                metrics=_metrics_by_scope(metrics_by_run.get(run.id, [])),
            )
        )

    return MetricsHistoryOut(owner=repo_obj.owner, repo=repo_obj.name, runs=results)


@router.get("/orgs/{owner}/metrics", response_model=List[MetricsOut])
def get_org_metrics(
    owner: str,
    session=Depends(get_db_session),
):
    repos = (
        session.execute(select(Repo).where(Repo.owner == owner).order_by(Repo.name))
        .scalars()
        .all()
    )
    results = []
    for repo_obj in repos:
        run = _get_latest_run(session, repo_obj.id)
        if not run:
            continue
        metrics = session.execute(select(Metric).where(Metric.run_id == run.id)).scalars().all()
        results.append(
            MetricsOut(
                owner=repo_obj.owner,
                repo=repo_obj.name,
                run=RunOut(
                    id=run.id,
                    run_started_at=run.run_started_at,
                    time_range=run.time_range,
                    since_date=run.since_date,
                ),
                metrics=_metrics_by_scope(metrics),
            )
        )
    return results
