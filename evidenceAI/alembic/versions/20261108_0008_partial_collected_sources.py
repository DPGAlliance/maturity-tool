"""Persist partial source collection metadata.

Revision ID: 20261108_0008
Revises: 20261108_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20261108_0008"
down_revision = "20261108_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collected_sources", sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("collected_sources", sa.Column("fetched_bytes", sa.Integer(), nullable=True))
    op.alter_column("collected_sources", "is_partial", server_default=None)


def downgrade() -> None:
    op.drop_column("collected_sources", "fetched_bytes")
    op.drop_column("collected_sources", "is_partial")
