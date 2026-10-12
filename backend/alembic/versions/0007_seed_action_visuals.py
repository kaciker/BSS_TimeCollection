"""Assign default illustrations to standard actions when unset.

Revision ID: 0007_seed_action_visuals
Revises: 0006_action_visuals
"""
from alembic import op

revision = "0007_seed_action_visuals"
down_revision = "0006_action_visuals"
branch_labels = None
depends_on = None

_DEFAULTS = {
    "END_WORK": "end-work",
    "BREAK": "break",
    "FACTORY_EXIT": "factory",
    "PERSONAL_MATTERS": "personal",
    "MEDICAL": "medical",
    "LEGAL_MATTERS": "legal",
    "NO_WORK": "no-work",
}


def upgrade() -> None:
    for code, visual_key in _DEFAULTS.items():
        op.execute(
            "UPDATE actions SET visual_key = '%s' WHERE code = '%s' AND visual_key IS NULL"
            % (visual_key, code)
        )


def downgrade() -> None:
    for code, visual_key in _DEFAULTS.items():
        op.execute(
            "UPDATE actions SET visual_key = NULL WHERE code = '%s' AND visual_key = '%s'"
            % (code, visual_key)
        )
