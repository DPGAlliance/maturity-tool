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


class SummaryIn(BaseModel):
    summary_text: str
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    run_id: Optional[int] = None
    metadata_json: Optional[Any] = None


class RepoScanValidateIn(BaseModel):
    repo_url: str


class RepoScanValidateOut(BaseModel):
    valid: bool
    provider: Optional[str] = None
    host: Optional[str] = None
    repo_path: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    canonical_repo_url: Optional[str] = None
    accessible: bool = False
    scan_supported: bool = False
    default_branch: Optional[str] = None
    archived: Optional[bool] = None
    visibility: Optional[str] = None
    error: Optional[str] = None


class RepoScanJobOut(BaseModel):
    scan_id: int
    provider: str
    host: str
    repo_path: str
    owner: Optional[str] = None
    repo: Optional[str] = None
    repo_url_raw: str
    canonical_repo_url: str
    status: str
    requested_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    run_id: Optional[int] = None
    status_url: Optional[str] = None
    result_url: Optional[str] = None
