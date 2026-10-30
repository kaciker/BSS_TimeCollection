"""Add reader identity visibility and perimeter identity snapshots.

Revision ID: 0016_person_badge_reader
Revises: 0015_person_badge_identity
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_person_badge_reader"
down_revision = "0015_person_badge_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("person_badge_assignments", sa.Column("reader_id", sa.String(length=32), nullable=True))
    op.create_index("ix_person_badge_assignments_reader_id", "person_badge_assignments", ["reader_id"])
    op.create_index(
        "ix_person_badge_assignments_factory_reader_active",
        "person_badge_assignments",
        ["factory_code", "reader_id", "observed_to"],
    )

    op.add_column("factory_perimeter_events", sa.Column("source_person_id", sa.String(length=50), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("person_id", sa.String(length=30), nullable=True))
    op.add_column("factory_perimeter_events", sa.Column("credential_id", sa.String(length=250), nullable=True))
    op.create_index("ix_factory_perimeter_events_source_person_id", "factory_perimeter_events", ["source_person_id"])
    op.create_index("ix_factory_perimeter_events_person_id", "factory_perimeter_events", ["person_id"])
    op.create_index("ix_factory_perimeter_events_credential_id", "factory_perimeter_events", ["credential_id"])


def downgrade():
    op.drop_index("ix_factory_perimeter_events_credential_id", table_name="factory_perimeter_events")
    op.drop_index("ix_factory_perimeter_events_person_id", table_name="factory_perimeter_events")
    op.drop_index("ix_factory_perimeter_events_source_person_id", table_name="factory_perimeter_events")
    op.drop_column("factory_perimeter_events", "credential_id")
    op.drop_column("factory_perimeter_events", "person_id")
    op.drop_column("factory_perimeter_events", "source_person_id")

    op.drop_index("ix_person_badge_assignments_factory_reader_active", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_reader_id", table_name="person_badge_assignments")
    op.drop_column("person_badge_assignments", "reader_id")
