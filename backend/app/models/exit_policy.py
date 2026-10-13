from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, String, Table, func, literal_column

from app.db.base import Base

policies = Table(
    "exit_policies", Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("terminal_id", Integer, ForeignKey("terminals.id", ondelete="CASCADE")),
    Column("mode", String(32), nullable=False),
    CheckConstraint("mode IN ('DISABLED', 'SAME_TERMINAL', 'SAME_WORK_CELL')", name="ck_exit_policy_mode"),
    CheckConstraint("terminal_id IS NULL OR terminal_id > 0", name="ck_exit_policy_scope"),
)
# PostgreSQL UNIQUE alone permits multiple NULL global scopes.
Index("uq_exit_policy_scope", func.coalesce(policies.c.terminal_id, literal_column("0")), unique=True)
