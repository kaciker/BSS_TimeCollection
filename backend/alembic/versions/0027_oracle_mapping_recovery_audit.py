"""Audit generic recovery of mapping-blocked Oracle events."""
from alembic import op
import sqlalchemy as sa

revision = "0027_oracle_map_recovery"
down_revision = "0026_securitydb_clock_correction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oracle_mapping_recovery_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=36), sa.ForeignKey("time_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("field_name", sa.String(length=80), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("source_action_id", sa.Integer(), sa.ForeignKey("actions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_action_code", sa.String(length=64), nullable=False),
        sa.Column("mapping_reference", sa.String(length=255), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("recovery_reason", sa.Text(), nullable=False),
        sa.UniqueConstraint("event_id", "field_name", name="uq_oracle_mapping_recovery_event_field"),
    )
    op.create_index("ix_oracle_mapping_recovery_audit_event_id", "oracle_mapping_recovery_audit", ["event_id"])
    op.create_index("ix_time_events_mapping_recovery_scan", "time_events", ["delivery_status", "attempt_count", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_time_events_mapping_recovery_scan", table_name="time_events")
    op.drop_index("ix_oracle_mapping_recovery_audit_event_id", table_name="oracle_mapping_recovery_audit")
    op.drop_table("oracle_mapping_recovery_audit")
