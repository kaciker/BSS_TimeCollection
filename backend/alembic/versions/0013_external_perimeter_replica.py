"""Track external perimeter replication cursor and health.

Revision ID: 0013_external_perimeter_replica
Revises: 0012_operational_metrics
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_external_perimeter_replica"
down_revision = "0012_operational_metrics"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "factory_perimeter_settings",
        sa.Column("external_last_log_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "factory_perimeter_settings",
        sa.Column("external_sync_initialized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "factory_perimeter_settings",
        sa.Column("external_last_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "factory_perimeter_settings",
        sa.Column("external_sync_error", sa.String(64), nullable=True),
    )


def downgrade():
    op.drop_column("factory_perimeter_settings", "external_sync_error")
    op.drop_column("factory_perimeter_settings", "external_last_sync_at")
    op.drop_column("factory_perimeter_settings", "external_sync_initialized_at")
    op.drop_column("factory_perimeter_settings", "external_last_log_id")
