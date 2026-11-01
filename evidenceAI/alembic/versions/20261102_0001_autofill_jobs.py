"""Create persistent MAT autofill jobs.

Revision ID: 20261102_0001
Revises:
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261102_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autofill_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.String(length=300), nullable=False),
        sa.Column("assessment_id", sa.String(length=300), nullable=False),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("product_version", sa.String(length=200), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("requested_indicators", sa.JSON(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_autofill_jobs_status", "autofill_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_autofill_jobs_status", table_name="autofill_jobs")
    op.drop_table("autofill_jobs")
