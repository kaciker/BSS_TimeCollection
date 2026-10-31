"""Retain the deployed observation marker migration for CORP compatibility.

Revision ID: 0020_observed_reader
Revises: 0019_external_source_txns

The CORP database already records this revision. Keeping it in the clean
integration's linear Alembic history lets new API images recognize and
continue that database revision without altering the existing schema.
"""
from alembic import op
import sqlalchemy as sa


revision = "0020_observed_reader"
down_revision = "0019_external_source_txns"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("person_badge_assignments", sa.Column("reader_id_observed", sa.Boolean(), nullable=True))
    op.execute("UPDATE person_badge_assignments SET reader_id_observed = FALSE")
    op.alter_column("person_badge_assignments", "reader_id_observed", nullable=False, server_default=sa.false())


def downgrade():
    op.drop_column("person_badge_assignments", "reader_id_observed")
