"""Add per-factory SECURITY_DB source clock correction and timestamp audit fields."""
from alembic import op
import sqlalchemy as sa

revision = "0026_securitydb_clock_correction"
down_revision = "0025_oracle_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "factory_perimeter_settings",
        sa.Column("source_clock_correction_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "factory_perimeter_settings",
        sa.Column("source_clock_offset_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_perimeter_source_clock_offset",
        "factory_perimeter_settings",
        "source_clock_offset_minutes >= -720 AND source_clock_offset_minutes <= 720",
    )
    op.add_column("factory_perimeter_events", sa.Column("source_event_datetime", sa.DateTime(timezone=True), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("effective_event_datetime", sa.DateTime(timezone=True), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("source_clock_offset_minutes", sa.Integer(), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("source_clock_correction_applied", sa.Boolean(), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("source_clock_correction_pending", sa.Boolean(), nullable=True))
    # Existing imported rows retain their current immutable interpretation until
    # an administrator explicitly activates correction. The source timestamp is
    # copied before any later effective-time transition.
    op.execute(sa.text("""
        UPDATE factory_perimeter_events
        SET source_event_datetime = event_datetime,
            effective_event_datetime = event_datetime,
            source_clock_offset_minutes = 0,
            source_clock_correction_applied = false,
            source_clock_correction_pending = true
        WHERE source_system = 'SQLSERVER_SECURITY_DB'
    """))


def downgrade() -> None:
    op.drop_column("factory_perimeter_events", "source_clock_correction_pending")
    op.drop_column("factory_perimeter_events", "source_clock_correction_applied")
    op.drop_column("factory_perimeter_events", "source_clock_offset_minutes")
    op.drop_column("factory_perimeter_events", "effective_event_datetime")
    op.drop_column("factory_perimeter_events", "source_event_datetime")
    op.drop_constraint("ck_perimeter_source_clock_offset", "factory_perimeter_settings", type_="check")
    op.drop_column("factory_perimeter_settings", "source_clock_offset_minutes")
    op.drop_column("factory_perimeter_settings", "source_clock_correction_enabled")
