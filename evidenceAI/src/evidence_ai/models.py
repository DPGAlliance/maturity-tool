from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from evidence_ai.db import Base


class AutofillJob(Base):
    __tablename__ = "autofill_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[str] = mapped_column(String(300), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(300), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    product_version: Mapped[str | None] = mapped_column(String(200))
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    requested_indicators: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(80), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
