"""Persist authoritative current factory presence separately from history.

Revision ID: 0022_factory_presence
Revises: 0021_factory_registry
"""
from alembic import op
import sqlalchemy as sa


revision = "0022_factory_presence"
down_revision = "0021_factory_registry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "factory_presence_projections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("factory_code", sa.String(64), sa.ForeignKey("factories.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("tracking_key", sa.String(320), nullable=False),
        sa.Column("person_id", sa.String(30), nullable=True),
        sa.Column("reader_id", sa.String(32), nullable=True),
        sa.Column("credential_id", sa.String(250), nullable=True),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("resolution_code", sa.String(64), nullable=False),
        sa.Column("source_movement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unresolved_reason", sa.String(64), nullable=True),
        sa.CheckConstraint("state IN ('INSIDE', 'OUTSIDE', 'UNKNOWN')", name="ck_factory_presence_state"),
        sa.UniqueConstraint("factory_code", "tracking_key", name="uq_factory_presence_tracking"),
    )
    op.create_index("ix_factory_presence_projections_person_id", "factory_presence_projections", ["person_id"])
    op.create_index("ix_factory_presence_projections_reader_id", "factory_presence_projections", ["reader_id"])
    op.create_index("ix_factory_presence_projections_credential_id", "factory_presence_projections", ["credential_id"])


def downgrade():
    op.drop_index("ix_factory_presence_projections_credential_id", table_name="factory_presence_projections")
    op.drop_index("ix_factory_presence_projections_reader_id", table_name="factory_presence_projections")
    op.drop_index("ix_factory_presence_projections_person_id", table_name="factory_presence_projections")
    op.drop_table("factory_presence_projections")
