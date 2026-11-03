"""Persist the HR-Path Oracle catalogue as operational data."""

from alembic import op
import sqlalchemy as sa

revision = "0025_oracle_catalogue"
down_revision = "0024_oracle_structure_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oracle_work_areas",
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_reference", sa.String(255), nullable=True),
    )
    op.create_table(
        "oracle_machines",
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("work_area_code", sa.String(80), sa.ForeignKey("oracle_work_areas.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_reference", sa.String(255), nullable=True),
    )
    op.create_index("ix_oracle_machines_work_area_code", "oracle_machines", ["work_area_code"])
    op.create_table(
        "oracle_cells",
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("machine_code", sa.String(80), sa.ForeignKey("oracle_machines.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_reference", sa.String(255), nullable=True),
    )
    op.create_index("ix_oracle_cells_machine_code", "oracle_cells", ["machine_code"])
    op.create_table(
        "oracle_payroll_time_types",
        sa.Column("code", sa.String(120), primary_key=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_reference", sa.String(255), nullable=True),
    )

    # Preserve only the explicitly verified catalogue facts. The complete HR-Path
    # workbook is not part of the deployment artifact and must be imported later.
    bind = op.get_bind()
    bind.execute(sa.text("INSERT INTO oracle_work_areas (code, description, active, source_reference) VALUES ('439', 'Acabado TP', true, 'HR-Path verified mapping')"))
    bind.execute(sa.text("INSERT INTO oracle_machines (code, description, work_area_code, active, source_reference) VALUES ('4391', 'T439.1', '439', true, 'HR-Path verified mapping'), ('4392', 'T439.2', '439', true, 'HR-Path verified mapping'), ('4393', 'T439.3 Recambios', '439', true, 'HR-Path verified mapping')"))
    bind.execute(sa.text("INSERT INTO oracle_cells (code, description, machine_code, active, source_reference) VALUES ('54Q', 'G.V. D34', '4391', true, 'HR-Path verified mapping'), ('54T', 'G.V. P24', '4391', true, 'HR-Path verified mapping'), ('54A', 'Lam y G.V. B75', '4393', true, 'HR-Path verified mapping')"))
    bind.execute(sa.text("INSERT INTO oracle_payroll_time_types (code, description, active, source_reference) VALUES ('Public Holiday ES', NULL, true, 'HR-Path verified mapping'), ('Workshop Entry ES', NULL, true, 'HR-Path verified mapping'), ('Project Entry ES', NULL, true, 'HR-Path verified mapping'), ('Non-productive time ES', NULL, true, 'HR-Path verified mapping'), ('Break ES', NULL, true, 'HR-Path verified mapping')"))
    op.create_foreign_key("fk_actions_oracle_payroll_time_type", "actions", "oracle_payroll_time_types", ["oracle_payroll_time_type"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_workshops_oracle_work_area", "workshops", "oracle_work_areas", ["oracle_work_area_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_subworkshops_oracle_machine", "subworkshops", "oracle_machines", ["oracle_machine_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_project_lines_oracle_cell", "project_lines", "oracle_cells", ["oracle_cell_code"], ["code"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_actions_oracle_payroll_time_type", "actions", type_="foreignkey")
    op.drop_constraint("fk_project_lines_oracle_cell", "project_lines", type_="foreignkey")
    op.drop_constraint("fk_subworkshops_oracle_machine", "subworkshops", type_="foreignkey")
    op.drop_constraint("fk_workshops_oracle_work_area", "workshops", type_="foreignkey")
    op.drop_table("oracle_payroll_time_types")
    op.drop_index("ix_oracle_cells_machine_code", table_name="oracle_cells")
    op.drop_table("oracle_cells")
    op.drop_index("ix_oracle_machines_work_area_code", table_name="oracle_machines")
    op.drop_table("oracle_machines")
    op.drop_table("oracle_work_areas")
