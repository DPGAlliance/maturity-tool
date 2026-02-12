from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RepoOut(BaseModel):
    owner: str
    name: str
    default_branch: Optional[str] = None


class RunOut(BaseModel):
    id: int
    run_started_at: datetime
    time_range: Optional[str] = None
    since_date: Optional[datetime] = None


class MetricsOut(BaseModel):
    owner: str
    repo: str
    run: RunOut
    metrics: Dict[str, Dict[str, Any]]


class MetricsHistoryOut(BaseModel):
    owner: str
    repo: str
    runs: List[MetricsOut]


class SummaryOut(BaseModel):
    id: int
    owner: str
    repo: Optional[str] = None
    summary_scope: str
    run_id: Optional[int] = None
    created_at: datetime
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    summary_text: str
    metadata_json: Optional[Any] = None
