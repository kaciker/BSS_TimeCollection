"""Allow active actions to be hidden from worker terminal menus.

Revision ID: 0011_action_visibility
Revises: 0010_factory_perimeter
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_action_visibility"
down_revision = "0010_factory_perimeter"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("actions", sa.Column("show_on_terminal", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("actions", "show_on_terminal")
