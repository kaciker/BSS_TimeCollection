"""Persist SECURITY_DB source transaction identity and overlap cursor.

Revision ID: 0019_external_source_txns
Revises: 0018_oracle_supplier
"""
from alembic import op
import sqlalchemy as sa


revision = "0019_external_source_txns"
down_revision = "0018_oracle_supplier"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("factory_perimeter_events", sa.Column("source_system", sa.String(64), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("source_transaction_id", sa.String(128), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("source_log_id", sa.BigInteger(), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("source_unique_key", sa.String(255), nullable=True))
    op.create_index(
        "ix_factory_perimeter_events_source_transaction",
        "factory_perimeter_events",
        ["factory_code", "source_system", "source_transaction_id"],
        unique=True,
        postgresql_where=sa.text("source_transaction_id IS NOT NULL"),
    )
    op.add_column("factory_perimeter_settings", sa.Column("external_sync_window_from", sa.DateTime(), nullable=True))
    op.add_column("factory_perimeter_settings", sa.Column("external_sync_cursor_created_at", sa.DateTime(), nullable=True))
    op.add_column("factory_perimeter_settings", sa.Column("external_sync_cursor_transaction_id", sa.String(128), nullable=True))


def downgrade():
    op.drop_column("factory_perimeter_settings", "external_sync_cursor_transaction_id")
    op.drop_column("factory_perimeter_settings", "external_sync_cursor_created_at")
    op.drop_column("factory_perimeter_settings", "external_sync_window_from")
    op.drop_index("ix_factory_perimeter_events_source_transaction", table_name="factory_perimeter_events")
    op.drop_column("factory_perimeter_events", "source_unique_key")
    op.drop_column("factory_perimeter_events", "source_log_id")
    op.drop_column("factory_perimeter_events", "source_transaction_id")
    op.drop_column("factory_perimeter_events", "source_system")
