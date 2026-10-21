"""Add bounded worker runtime telemetry for the operational metrics API.

Revision ID: 0012_operational_metrics
Revises: 0011_action_visibility
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_operational_metrics"
down_revision = "0011_action_visibility"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "worker_runtime_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_cycle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_worker_runtime_metrics_singleton"),
    )


def downgrade():
    op.drop_table("worker_runtime_metrics")
