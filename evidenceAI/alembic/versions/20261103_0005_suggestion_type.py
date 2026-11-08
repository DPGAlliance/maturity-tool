"""Separate evidence and capability drafts.

Revision ID: 20261103_0005
Revises: 20261103_0004
"""

from alembic import op
import sqlalchemy as sa

revision = "20261103_0005"
down_revision = "20261103_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_suggestions", sa.Column("suggestion_type", sa.String(length=20), nullable=False, server_default="evidence"))
    op.alter_column("evidence_suggestions", "suggestion_type", server_default=None)


def downgrade() -> None:
    op.drop_column("evidence_suggestions", "suggestion_type")
