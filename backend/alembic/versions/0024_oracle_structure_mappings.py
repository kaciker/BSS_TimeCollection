"""Store Oracle mappings on operational structure and freeze them per event."""

from alembic import op
import sqlalchemy as sa

revision = "0024_oracle_structure_mappings"
down_revision = "0023_attempt_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workshops", sa.Column("oracle_work_area_code", sa.String(length=80), nullable=True))
    op.add_column("subworkshops", sa.Column("oracle_machine_code", sa.String(length=80), nullable=True))
    op.add_column("project_lines", sa.Column("oracle_cell_code", sa.String(length=80), nullable=True))
    op.add_column("time_events", sa.Column("oracle_work_area_code", sa.String(length=80), nullable=True))
    op.add_column("time_events", sa.Column("oracle_machine_code", sa.String(length=80), nullable=True))
    op.add_column("time_events", sa.Column("oracle_cell_code", sa.String(length=80), nullable=True))
    # START_WORK is an explicit normal workshop-entry action. Historical events
    # are deliberately not changed by this configuration update.
    bind = op.get_bind()
    action = bind.execute(sa.text("SELECT state_effect, oracle_supplier_event FROM actions WHERE code = 'START_WORK'")).mappings().first()
    if action and action["state_effect"] == "ENTER":
        bind.execute(sa.text("UPDATE actions SET oracle_payroll_time_type = 'Workshop Entry ES', oracle_supplier_event = 'HUT_TCD_SUPP1_IN_2' WHERE code = 'START_WORK'"))


def downgrade() -> None:
    op.drop_column("time_events", "oracle_cell_code")
    op.drop_column("time_events", "oracle_machine_code")
    op.drop_column("time_events", "oracle_work_area_code")
    op.drop_column("project_lines", "oracle_cell_code")
    op.drop_column("subworkshops", "oracle_machine_code")
    op.drop_column("workshops", "oracle_work_area_code")
