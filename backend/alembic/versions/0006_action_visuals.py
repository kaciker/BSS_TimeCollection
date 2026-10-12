"""Add optional visual key to actions.

Revision ID: 0006_action_visuals
Revises: 0005_terminal_soft_delete
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_action_visuals"
down_revision = "0005_terminal_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("actions", sa.Column("visual_key", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("actions", "visual_key")
