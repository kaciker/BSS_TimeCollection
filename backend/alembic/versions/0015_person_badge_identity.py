"""Add person identity snapshots and observed badge assignment history.

Revision ID: 0015_person_badge_identity
Revises: 0014_terminal_exit_menu_timeout
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_person_badge_identity"
down_revision = "0014_terminal_exit_menu_timeout"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("time_events", sa.Column("source_person_id", sa.String(length=50), nullable=True))
    op.add_column("time_events", sa.Column("person_id", sa.String(length=30), nullable=True))
    op.add_column("time_events", sa.Column("credential_id", sa.String(length=250), nullable=True))
    op.add_column("time_events", sa.Column("oracle_reporter_id", sa.String(length=80), nullable=True))
    op.add_column("time_events", sa.Column("oracle_reporter_id_type", sa.String(length=16), nullable=True))
    op.create_index("ix_time_events_source_person_id", "time_events", ["source_person_id"])
    op.create_index("ix_time_events_person_id", "time_events", ["person_id"])
    op.create_index("ix_time_events_credential_id", "time_events", ["credential_id"])

    op.create_table(
        "person_badge_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_code", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_person_id", sa.String(length=50), nullable=False),
        sa.Column("person_id", sa.String(length=30), nullable=False),
        sa.Column("source_card_id", sa.String(length=50), nullable=False),
        sa.Column("credential_id", sa.String(length=250), nullable=False),
        sa.Column("observed_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_person_badge_assignments_factory_code", "person_badge_assignments", ["factory_code"])
    op.create_index("ix_person_badge_assignments_source_person_id", "person_badge_assignments", ["source_person_id"])
    op.create_index("ix_person_badge_assignments_person_id", "person_badge_assignments", ["person_id"])
    op.create_index("ix_person_badge_assignments_credential_id", "person_badge_assignments", ["credential_id"])
    op.create_index("ix_person_badge_assignments_observed_from", "person_badge_assignments", ["observed_from"])
    op.create_index("ix_person_badge_assignments_observed_to", "person_badge_assignments", ["observed_to"])
    op.create_index(
        "ix_person_badge_assignments_factory_person_active",
        "person_badge_assignments",
        ["factory_code", "source_person_id", "observed_to"],
    )
    op.create_index(
        "ix_person_badge_assignments_factory_credential_active",
        "person_badge_assignments",
        ["factory_code", "credential_id", "observed_to"],
    )


def downgrade():
    op.drop_index("ix_person_badge_assignments_factory_credential_active", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_factory_person_active", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_observed_to", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_observed_from", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_credential_id", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_person_id", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_source_person_id", table_name="person_badge_assignments")
    op.drop_index("ix_person_badge_assignments_factory_code", table_name="person_badge_assignments")
    op.drop_table("person_badge_assignments")

    op.drop_index("ix_time_events_credential_id", table_name="time_events")
    op.drop_index("ix_time_events_person_id", table_name="time_events")
    op.drop_index("ix_time_events_source_person_id", table_name="time_events")
    op.drop_column("time_events", "oracle_reporter_id_type")
    op.drop_column("time_events", "oracle_reporter_id")
    op.drop_column("time_events", "credential_id")
    op.drop_column("time_events", "person_id")
    op.drop_column("time_events", "source_person_id")
