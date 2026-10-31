"""Persist factory registry and installation factory selection.

Revision ID: 0021_factory_registry
Revises: 0020_observed_reader
"""
from alembic import op
import sqlalchemy as sa


revision = "0021_factory_registry"
down_revision = "0020_observed_reader"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "factories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("location", sa.String(160), nullable=True),
        sa.Column("country", sa.String(80), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "installation_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("default_factory_code", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    bind = op.get_bind()
    codes = bind.execute(sa.text("""
        SELECT factory_code AS code FROM terminals WHERE factory_code IS NOT NULL
        UNION SELECT factory_code FROM factory_perimeter_settings
        UNION SELECT factory_code FROM factory_perimeter_events
        UNION SELECT factory_code FROM person_badge_assignments
        UNION SELECT factory_code FROM terminal_badge_reads
    """)).scalars().all()
    for code in sorted({str(value) for value in codes if value and str(value).strip()}):
        # Keep legacy references intact but make the old placeholder unavailable
        # for new assignments. Its rows remain readable for audit purposes.
        active = code.strip().upper() not in {"DEFAULT", "UNASSIGNED"}
        name, location, country, timezone = code, None, None, "UTC"
        bind.execute(sa.text("INSERT INTO factories(code,name,location,country,timezone,active) VALUES (:code,:name,:location,:country,:timezone,:active)"),
                     {"code": code, "name": name, "location": location, "country": country, "timezone": timezone, "active": active})

    if bind.execute(sa.text("SELECT count(*) FROM terminals WHERE factory_code IS NULL")).scalar_one():
        raise RuntimeError("Factory migration found terminals without an explicit factory assignment; assign them before upgrading")

    active_codes = bind.execute(sa.text("SELECT code FROM factories WHERE active ORDER BY code")).scalars().all()
    # A unique active factory is an unambiguous installation default. Multiple
    # candidates require an administrator to make an explicit selection.
    default_code = active_codes[0] if len(active_codes) == 1 else None
    bind.execute(sa.text("INSERT INTO installation_settings(id,default_factory_code) VALUES (1,:code)"), {"code": default_code})

    op.alter_column("terminals", "factory_code", nullable=False, server_default=None)
    op.create_foreign_key("fk_terminals_factory_code_factories", "terminals", "factories", ["factory_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_factory_perimeter_settings_factory", "factory_perimeter_settings", "factories", ["factory_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_factory_perimeter_events_factory", "factory_perimeter_events", "factories", ["factory_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_person_badge_assignments_factory", "person_badge_assignments", "factories", ["factory_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_terminal_badge_reads_factory", "terminal_badge_reads", "factories", ["factory_code"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("fk_installation_default_factory", "installation_settings", "factories", ["default_factory_code"], ["code"], ondelete="RESTRICT")


def downgrade():
    op.drop_constraint("fk_installation_default_factory", "installation_settings", type_="foreignkey")
    op.drop_constraint("fk_factory_perimeter_settings_factory", "factory_perimeter_settings", type_="foreignkey")
    op.drop_constraint("fk_factory_perimeter_events_factory", "factory_perimeter_events", type_="foreignkey")
    op.drop_constraint("fk_person_badge_assignments_factory", "person_badge_assignments", type_="foreignkey")
    op.drop_constraint("fk_terminal_badge_reads_factory", "terminal_badge_reads", type_="foreignkey")
    op.drop_constraint("fk_terminals_factory_code_factories", "terminals", type_="foreignkey")
    op.drop_table("installation_settings")
    op.drop_table("factories")
