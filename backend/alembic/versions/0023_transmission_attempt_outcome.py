"""Persist retry ambiguity and returned Oracle IDs per attempt."""

from alembic import op
import sqlalchemy as sa

revision = "0023_transmission_attempt_outcome"
down_revision = "0022_factory_presence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transmission_attempts", sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("transmission_attempts", sa.Column("ambiguous", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("transmission_attempts", sa.Column("oracle_request_id", sa.String(length=128), nullable=True))
    op.add_column("transmission_attempts", sa.Column("oracle_event_id", sa.String(length=128), nullable=True))
    op.alter_column("transmission_attempts", "retryable", server_default=None)
    op.alter_column("transmission_attempts", "ambiguous", server_default=None)


def downgrade() -> None:
    op.drop_column("transmission_attempts", "oracle_event_id")
    op.drop_column("transmission_attempts", "oracle_request_id")
    op.drop_column("transmission_attempts", "ambiguous")
    op.drop_column("transmission_attempts", "retryable")
