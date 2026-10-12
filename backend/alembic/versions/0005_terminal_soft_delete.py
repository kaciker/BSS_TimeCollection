"""Allow terminals to be removed from administration without losing event history.

Revision ID: 0005_terminal_soft_delete
Revises: 0004_action_subactions
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_terminal_soft_delete"
down_revision = "0004_action_subactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("terminals", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("terminals", "deleted_at")
