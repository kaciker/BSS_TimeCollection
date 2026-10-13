"""Three-level structure and nullable historical snapshots.
Revision ID: 0009_operational_structure
Revises: 0008_exit_policies
"""
from alembic import op
import sqlalchemy as sa
revision = "0009_operational_structure"
down_revision = "0008_exit_policies"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("workshops", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(64), nullable=False), sa.Column("description", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("code", name="uq_workshop_code"))
    op.create_table("subworkshops", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("workshop_id", sa.Integer(), sa.ForeignKey("workshops.id", ondelete="RESTRICT"), nullable=False), sa.Column("code", sa.String(64), nullable=False), sa.Column("description", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("workshop_id", "code", name="uq_subworkshop_parent_code"))
    op.create_table("project_lines", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("subworkshop_id", sa.Integer(), sa.ForeignKey("subworkshops.id", ondelete="RESTRICT"), nullable=False), sa.Column("code", sa.String(64), nullable=False), sa.Column("description", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("subworkshop_id", "code", name="uq_project_line_parent_code"))
    op.add_column("terminals", sa.Column("project_line_id", sa.Integer(), sa.ForeignKey("project_lines.id", ondelete="RESTRICT"), nullable=True))
    op.create_index("ix_terminals_project_line_id", "terminals", ["project_line_id"])
    for field in ("workshop_code", "subworkshop_code", "project_line_code"):
        op.add_column("time_events", sa.Column(field, sa.String(64), nullable=True))
    for field in ("workshop_description", "subworkshop_description", "project_line_description"):
        op.add_column("time_events", sa.Column(field, sa.String(255), nullable=True))

def downgrade():
    raise RuntimeError("Downgrade would erase structure and snapshots; restore a verified backup instead")
