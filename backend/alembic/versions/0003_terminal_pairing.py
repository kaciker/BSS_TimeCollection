"""Add browser initiated terminal pairing.

Revision ID: 0003_terminal_pairing
Revises: 0002_terminal_identity_context
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_terminal_pairing"
down_revision = "0002_terminal_identity_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terminal_pairing_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("request_token_hash", sa.String(64), nullable=False),
        sa.Column("terminal_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["terminal_id"], ["terminals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_terminal_pairing_requests_code_hash", "terminal_pairing_requests", ["code_hash"], unique=True)
    op.create_index("ix_terminal_pairing_requests_request_token_hash", "terminal_pairing_requests", ["request_token_hash"], unique=True)
    op.create_index("ix_terminal_pairing_requests_terminal_id", "terminal_pairing_requests", ["terminal_id"])
    op.create_index("ix_terminal_pairing_requests_status", "terminal_pairing_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_terminal_pairing_requests_status", table_name="terminal_pairing_requests")
    op.drop_index("ix_terminal_pairing_requests_terminal_id", table_name="terminal_pairing_requests")
    op.drop_index("ix_terminal_pairing_requests_request_token_hash", table_name="terminal_pairing_requests")
    op.drop_index("ix_terminal_pairing_requests_code_hash", table_name="terminal_pairing_requests")
    op.drop_table("terminal_pairing_requests")
