"""Persist bounded investigation actions.

Revision ID: 20261108_0007
Revises: 20261108_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20261108_0007"
down_revision = "20261108_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("requested", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["autofill_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_investigation_actions_job_id", "investigation_actions", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_investigation_actions_job_id", table_name="investigation_actions")
    op.drop_table("investigation_actions")
