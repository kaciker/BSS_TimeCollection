"""Optional factory perimeter and badge scan deduplication.

Revision ID: 0010_factory_perimeter
Revises: 0009_operational_structure
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_factory_perimeter"
down_revision = "0009_operational_structure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "factory_perimeter_settings",
        sa.Column("factory_code", sa.String(64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("badge_source", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("dedup_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("dedup_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("auto_exit_action_code", sa.String(64), nullable=True),
        sa.CheckConstraint("dedup_seconds >= 0 AND dedup_seconds <= 300", name="ck_perimeter_dedup_seconds"),
        sa.CheckConstraint("badge_source IN ('OPEN', 'EXTERNAL')", name="ck_perimeter_badge_source"),
    )
    op.create_table(
        "factory_perimeter_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("factory_code", sa.String(64), nullable=False),
        sa.Column("reporter_id", sa.String(160), nullable=False),
        sa.Column("terminal_id", sa.Integer(), sa.ForeignKey("terminals.id"), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("event_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("auto_cell_exit_event_id", sa.String(36), sa.ForeignKey("time_events.id"), nullable=True),
        sa.CheckConstraint("direction IN ('ENTER', 'EXIT')", name="ck_perimeter_direction"),
    )
    op.create_index("ix_perimeter_presence", "factory_perimeter_events", ["factory_code", "reporter_id", "event_datetime"])
    op.create_table(
        "terminal_badge_reads",
        sa.Column("factory_code", sa.String(64), primary_key=True),
        sa.Column("terminal_id", sa.Integer(), sa.ForeignKey("terminals.id"), primary_key=True),
        sa.Column("reporter_id", sa.String(160), primary_key=True),
        sa.Column("last_recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("terminals", sa.Column("factory_code", sa.String(64), nullable=False, server_default="DEFAULT"))
    op.add_column("terminals", sa.Column("terminal_role", sa.String(16), nullable=False, server_default="CELL"))


def downgrade():
    op.drop_constraint("ck_terminal_role", "terminals", type_="check")
    op.drop_column("terminals", "terminal_role")
    op.drop_column("terminals", "factory_code")
    op.drop_table("terminal_badge_reads")
    op.drop_index("ix_perimeter_presence", table_name="factory_perimeter_events")
    op.drop_table("factory_perimeter_events")
    op.drop_table("factory_perimeter_settings")
