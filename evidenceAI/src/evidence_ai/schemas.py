from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProvidedResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    source: str = Field(min_length=1, max_length=100)


class AutofillContextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_name: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    website_url: str | None = Field(default=None, max_length=2048)
    documentation_urls: list[str] = Field(default_factory=list, max_length=20)
    repository_url: str | None = Field(default=None, max_length=2048)
    provided_resources: list[ProvidedResourceIn] = Field(default_factory=list, max_length=50)


class AutofillJobCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=300)
    assessment_id: str = Field(min_length=1, max_length=300)
    product_name: str = Field(min_length=1, max_length=500)
    product_version: str | None = Field(default=None, max_length=200)
    context: AutofillContextIn = Field(default_factory=AutofillContextIn)
    requested_indicators: list[str] = Field(default_factory=lambda: ["all"], max_length=20)


class AutofillJobCreatedOut(BaseModel):
    job_id: UUID
    product_id: str
    assessment_id: str
    status: Literal["pending", "running", "completed", "completed_with_warnings", "failed"]
    stage: str
    status_url: str


class AutofillJobStatusOut(BaseModel):
    job_id: UUID
    product_id: str
    assessment_id: str
    status: Literal["pending", "running", "completed", "completed_with_warnings", "failed"]
    stage: str
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
