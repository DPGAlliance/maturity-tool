"""Create generation trace records.

Revision ID: 20261103_0004
Revises: 20261102_0003
Create Date: 2026-11-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20261103_0004"
down_revision = "20261102_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["autofill_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_attempts_job_id", "generation_attempts", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_generation_attempts_job_id", table_name="generation_attempts")
    op.drop_table("generation_attempts")
