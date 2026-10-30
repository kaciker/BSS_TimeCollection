"""Add HR-Path Oracle action fields and permit shared supplier events.

Revision ID: 0017_oracle_hrpath
Revises: 0016_person_badge_reader
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_oracle_hrpath"
down_revision = "0016_person_badge_reader"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("actions", sa.Column("oracle_payroll_time_type", sa.String(length=120), nullable=True))
    op.add_column("time_events", sa.Column("oracle_payroll_time_type", sa.String(length=120), nullable=True))
    op.add_column("time_events", sa.Column("oracle_mapping_error", sa.String(length=255), nullable=True))
    op.execute("UPDATE actions SET oracle_payroll_time_type = oracle_attributes ->> 'PayrollTimeType' WHERE oracle_attributes::jsonb ? 'PayrollTimeType'")
    op.execute("UPDATE time_events SET oracle_payroll_time_type = oracle_attributes ->> 'PayrollTimeType' WHERE oracle_attributes::jsonb ? 'PayrollTimeType'")
    op.execute("""
        UPDATE time_events SET oracle_mapping_error = CASE
            WHEN person_id IS NULL THEN 'Resolved Person ID is missing; event requires identity reconciliation'
            ELSE 'Workshop / Subworkshop / Project-Line snapshot is incomplete'
        END
        WHERE person_id IS NULL OR workshop_code IS NULL OR subworkshop_code IS NULL OR project_line_code IS NULL
    """)
    op.drop_constraint("actions_supplier_device_event_key", "actions", type_="unique")


def downgrade():
    op.create_unique_constraint("actions_supplier_device_event_key", "actions", ["supplier_device_event"])
    op.drop_column("time_events", "oracle_mapping_error")
    op.drop_column("time_events", "oracle_payroll_time_type")
    op.drop_column("actions", "oracle_payroll_time_type")
