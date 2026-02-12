from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select

from api.deps import get_db_session, require_api_key
from api.schemas import RepoOut
from storage.models import Repo


router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("", response_model=List[RepoOut], dependencies=[Depends(require_api_key)])
def list_repos(owner: Optional[str] = None, session=Depends(get_db_session)):
    query = select(Repo)
    if owner:
        query = query.where(Repo.owner == owner)
    repos = session.execute(query.order_by(Repo.owner, Repo.name)).scalars().all()
    return [
        RepoOut(owner=repo.owner, name=repo.name, default_branch=repo.default_branch)
        for repo in repos
    ]
