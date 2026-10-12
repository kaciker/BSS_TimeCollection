"""Add hierarchical exit actions.

Revision ID: 0004_action_subactions
Revises: 0003_terminal_pairing
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_action_subactions"
down_revision = "0003_terminal_pairing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("actions", sa.Column("requires_subaction", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("actions", sa.Column("parent_action_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_actions_parent_action_id_actions",
        "actions",
        "actions",
        ["parent_action_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_actions_parent_action_id", "actions", ["parent_action_id"])


def downgrade() -> None:
    op.drop_index("ix_actions_parent_action_id", table_name="actions")
    op.drop_constraint("fk_actions_parent_action_id_actions", "actions", type_="foreignkey")
    op.drop_column("actions", "parent_action_id")
    op.drop_column("actions", "requires_subaction")
