"""Create collected source records.

Revision ID: 20261102_0002
Revises: 20261102_0001
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261102_0002"
down_revision = "20261102_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collected_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["autofill_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collected_sources_job_id", "collected_sources", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_collected_sources_job_id", table_name="collected_sources")
    op.drop_table("collected_sources")
