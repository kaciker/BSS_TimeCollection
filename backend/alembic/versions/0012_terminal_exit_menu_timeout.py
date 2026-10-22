"""Add a configurable timeout for the terminal exit menu.

Revision ID: 0012_terminal_exit_menu_timeout
Revises: 0011_action_visibility
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_terminal_exit_menu_timeout"
down_revision = "0011_action_visibility"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "terminals",
        sa.Column("exit_menu_timeout_seconds", sa.Integer(), server_default="5", nullable=False),
    )


def downgrade():
    op.drop_column("terminals", "exit_menu_timeout_seconds")
