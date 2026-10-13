"""Version exit policy storage and enforce one row per scope.

Revision ID: 0008_exit_policies
Revises: 0007_seed_action_visuals
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_exit_policies"
down_revision = "0007_seed_action_visuals"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("exit_policies"):
        op.create_table(
            "exit_policies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("terminal_id", sa.Integer(), sa.ForeignKey("terminals.id", ondelete="CASCADE")),
            sa.Column("mode", sa.String(32), nullable=False),
            sa.CheckConstraint("mode IN ('DISABLED', 'SAME_TERMINAL', 'SAME_WORK_CELL')", name="ck_exit_policy_mode"),
            sa.CheckConstraint("terminal_id IS NULL OR terminal_id > 0", name="ck_exit_policy_scope"),
        )
    else:
        # Adopt installations that ran the unversioned GitHub startup DDL.
        # Never silently choose among conflicting configuration rows.
        duplicate = bind.execute(sa.text("SELECT coalesce(terminal_id, 0) FROM exit_policies GROUP BY coalesce(terminal_id, 0) HAVING count(*) > 1")).first()
        invalid = bind.execute(sa.text("SELECT p.id FROM exit_policies p LEFT JOIN terminals t ON t.id=p.terminal_id WHERE p.mode NOT IN ('DISABLED','SAME_TERMINAL','SAME_WORK_CELL') OR p.mode IS NULL OR (p.terminal_id IS NOT NULL AND (p.terminal_id<=0 OR t.id IS NULL))")).first()
        if duplicate or invalid:
            raise RuntimeError("Existing exit policies contain duplicate scopes or invalid settings; reconcile them before migration. No policy has been overwritten.")
        with op.batch_alter_table("exit_policies") as batch:
            checks = {c['name'] for c in inspector.get_check_constraints("exit_policies")}
            if "ck_exit_policy_mode" not in checks:
                batch.create_check_constraint("ck_exit_policy_mode", "mode IN ('DISABLED', 'SAME_TERMINAL', 'SAME_WORK_CELL')")
            if "ck_exit_policy_scope" not in checks:
                batch.create_check_constraint("ck_exit_policy_scope", "terminal_id IS NULL OR terminal_id > 0")
            if not inspector.get_foreign_keys("exit_policies"):
                batch.create_foreign_key("fk_exit_policy_terminal", "terminals", ["terminal_id"], ["id"], ondelete="CASCADE")
    if "uq_exit_policy_scope" not in {i['name'] for i in sa.inspect(bind).get_indexes("exit_policies")}:
        op.create_index("uq_exit_policy_scope", "exit_policies", [sa.text("coalesce(terminal_id, 0)")], unique=True)
    # Empty storage resolves to Disabled; no default is changed or seeded.


def downgrade():
    op.drop_table("exit_policies")
