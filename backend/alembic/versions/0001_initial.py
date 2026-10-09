"""Initial schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terminals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("external_device_id", sa.String(128), nullable=False, unique=True),
        sa.Column("identification_mode", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("supplier_device_event", sa.String(128), nullable=False, unique=True),
        sa.Column("state_effect", sa.String(16), nullable=False),
        sa.Column("reporter_id_type", sa.String(16), nullable=False, server_default="BADGE"),
        sa.Column("oracle_attributes", sa.JSON(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "terminal_actions",
        sa.Column("terminal_id", sa.Integer(), sa.ForeignKey("terminals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("action_id", sa.Integer(), sa.ForeignKey("actions.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "time_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_number", sa.String(128), nullable=False, unique=True),
        sa.Column("terminal_id", sa.Integer(), sa.ForeignKey("terminals.id"), nullable=False),
        sa.Column("action_id", sa.Integer(), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("terminal_code", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("action_code", sa.String(64), nullable=False),
        sa.Column("action_label", sa.String(120), nullable=False),
        sa.Column("supplier_device_event", sa.String(128), nullable=False),
        sa.Column("state_effect", sa.String(16), nullable=False),
        sa.Column("reporter_id", sa.String(160), nullable=False),
        sa.Column("reporter_id_type", sa.String(16), nullable=False),
        sa.Column("identification_method", sa.String(16), nullable=False),
        sa.Column("event_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_timezone", sa.String(64), nullable=False),
        sa.Column("oracle_attributes", sa.JSON(), nullable=False),
        sa.Column("delivery_status", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oracle_request_id", sa.String(128), nullable=True),
        sa.Column("oracle_event_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_time_events_reporter_datetime", "time_events", ["reporter_id", "event_datetime"])
    op.create_index("ix_time_events_delivery", "time_events", ["delivery_status", "next_attempt_at"])
    op.create_table(
        "transmission_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("time_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_transmission_attempts_event", "transmission_attempts", ["event_id", "attempt_number"])


def downgrade() -> None:
    op.drop_index("ix_transmission_attempts_event", table_name="transmission_attempts")
    op.drop_table("transmission_attempts")
    op.drop_index("ix_time_events_delivery", table_name="time_events")
    op.drop_index("ix_time_events_reporter_datetime", table_name="time_events")
    op.drop_table("time_events")
    op.drop_table("terminal_actions")
    op.drop_table("actions")
    op.drop_table("terminals")
