"""Add terminal browser identity and configurable Oracle context.

Revision ID: 0002_terminal_identity_context
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_terminal_identity_context"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("terminals", sa.Column("reporter_id_type", sa.String(16), nullable=False, server_default="BADGE"))
    op.add_column("terminals", sa.Column("oracle_attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("terminals", sa.Column("activation_token_hash", sa.String(64), nullable=True))
    op.add_column("terminals", sa.Column("session_token_hash", sa.String(64), nullable=True))
    op.add_column("terminals", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("terminals", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("terminals", sa.Column("last_ip", sa.String(64), nullable=True))
    op.add_column("terminals", sa.Column("last_user_agent", sa.String(512), nullable=True))
    op.create_index("ix_terminals_activation_token_hash", "terminals", ["activation_token_hash"], unique=True)
    op.create_index("ix_terminals_session_token_hash", "terminals", ["session_token_hash"], unique=True)
    op.drop_index("ix_time_events_reporter_datetime", table_name="time_events")
    op.create_index(
        "ix_time_events_reporter_datetime_created",
        "time_events",
        ["reporter_id", "event_datetime", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_time_events_reporter_datetime_created", table_name="time_events")
    op.create_index("ix_time_events_reporter_datetime", "time_events", ["reporter_id", "event_datetime"])
    op.drop_index("ix_terminals_session_token_hash", table_name="terminals")
    op.drop_index("ix_terminals_activation_token_hash", table_name="terminals")
    op.drop_column("terminals", "last_user_agent")
    op.drop_column("terminals", "last_ip")
    op.drop_column("terminals", "last_seen_at")
    op.drop_column("terminals", "activated_at")
    op.drop_column("terminals", "session_token_hash")
    op.drop_column("terminals", "activation_token_hash")
    op.drop_column("terminals", "oracle_attributes")
    op.drop_column("terminals", "reporter_id_type")
