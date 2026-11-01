"""Create AI draft suggestions.

Revision ID: 20261102_0003
Revises: 20261102_0002
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261102_0003"
down_revision = "20261102_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("indicator_id", sa.String(length=300), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["autofill_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_suggestions_job_id", "evidence_suggestions", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_suggestions_job_id", table_name="evidence_suggestions")
    op.drop_table("evidence_suggestions")
