"""Snapshot Oracle directional supplier events independently of local action codes.

Revision ID: 0018_oracle_supplier
Revises: 0017_oracle_hrpath
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_oracle_supplier"
down_revision = "0017_oracle_hrpath"
branch_labels = None
depends_on = None


def upgrade():
    # Remain compatible with databases where 0017 retained the legacy
    # uniqueness constraint on local BSS supplier events.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'actions'::regclass
                  AND conname = 'actions_supplier_device_event_key'
            ) THEN
                ALTER TABLE actions DROP CONSTRAINT actions_supplier_device_event_key;
            END IF;
        END $$
    """)
    op.add_column("actions", sa.Column("oracle_supplier_event", sa.String(length=40), nullable=True))
    op.execute("UPDATE actions SET oracle_supplier_event = CASE WHEN state_effect = 'ENTER' THEN 'HUT_TCD_SUPP1_IN_2' ELSE 'HUT_TCD_SUPP1_OUT_2' END")
    op.alter_column("actions", "oracle_supplier_event", nullable=False)
    op.add_column("time_events", sa.Column("oracle_supplier_event", sa.String(length=40), nullable=True))
    op.execute("UPDATE time_events SET oracle_supplier_event = CASE WHEN state_effect = 'ENTER' THEN 'HUT_TCD_SUPP1_IN_2' ELSE 'HUT_TCD_SUPP1_OUT_2' END")


def downgrade():
    op.drop_column("time_events", "oracle_supplier_event")
    op.drop_column("actions", "oracle_supplier_event")
