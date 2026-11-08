"""Store source links for bounded follow-up collection.

Revision ID: 20261108_0006
Revises: 20261103_0005
"""

from alembic import op
import sqlalchemy as sa

revision = "20261108_0006"
down_revision = "20261103_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collected_sources", sa.Column("links", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("collected_sources", "links", server_default=None)


def downgrade() -> None:
    op.drop_column("collected_sources", "links")
