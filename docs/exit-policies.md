# Terminal exit policies

Administration: `/admin/policies` holds the **global** Same Terminal Exit policy.
Individual policies and work cells belong to **Terminals → Edit → Exit policy**.

- `DISABLED` (default): any active terminal may capture an exit.
- `SAME_TERMINAL`: exit terminal ID must equal the ID of the last ENTER event.
- `SAME_WORK_CELL`: both entry and exit terminals must have the same valid
  `work_cell` in their **current** `oracle_attributes` configuration. Missing,
  invalid or different cells reject the exit, including on the same terminal.

Global settings apply unless a terminal override is selected. `INHERIT` deletes
that override. A new/cloned terminal inherits global settings. Disabled remains
the global fallback; migrations do not seed or change the selected global mode.
Deleted terminals are hidden from terminal configuration, with historical events retained.

Work cells can be edited in each terminal's options. Values are trimmed, case-sensitive
strings of up to 64 characters. Blank removes the cell; all other Oracle
attributes are preserved. Terminal creation/editing also validates `work_cell`.
Changing an entry terminal's cell changes subsequent Same Work Cell checks;
historical events and Oracle attribute snapshots are never rewritten.

Terminal creation/update accepts optional `exit_policy_mode` and saves the policy,
cell and other terminal settings atomically. Omission preserves the existing
override for older API clients. New terminals default to INHERIT. Cancel in the
editor applies no changes. Terminal reads expose the explicit, effective and
global modes; no schema migration is needed for this UI relocation.

Configuration endpoints:

- `GET /api/v1/admin/policies/same-terminal-exit`
- `PUT /api/v1/admin/policies/same-terminal-exit` with `{"mode":"DISABLED"}`
- `PUT /api/v1/admin/policies/same-terminal-exit/terminals/{code}` with
  `{"mode":"INHERIT"}` (or an explicit mode)
- `PUT /api/v1/admin/policies/same-terminal-exit/terminals/{code}/work-cell`
  with `{"work_cell":"CELL-1"}` (or `""` to remove)

Both scan and final exit capture enforce the effective policy, including parent
menus and sub-actions. Rejection returns HTTP 409 with the entry terminal/cell
or missing-configuration guidance and states that no exit was recorded. It
creates **no TimeEvent or TransmissionAttempt**, so no rejected exit is queued
or sent to Oracle. No attendance or payroll rules are implemented here.

Alembic `0008_exit_policies` owns the schema. Importing the API never performs
DDL. Foreign-key/check constraints and a unique `coalesce(terminal_id,0)` index
protect each scope, including the NULL global scope. Atomic upserts handle
concurrent saves. PostgreSQL transaction advisory locks serialize capture by
badge across terminals, including badges with no events; simultaneous final
exits can create at most one exit for the current entry. State and entry queries
use the same deterministic timestamp/ID ordering.

The migration can adopt the original unversioned table without replacing valid
settings. Conflicting duplicate scopes or invalid/orphan settings fail with an
explicit reconciliation error instead of silently deleting configuration.
Always back up PostgreSQL before migration. Downgrade removes the policy table;
use the database backup if policy configuration must be restored.

Validation:

- `pytest` covers modes, inheritance, cell configuration, latest entry,
  policy changes between menu and capture, and no Oracle queue on rejection.
- PostgreSQL checks in `tests/test_exit_policy_postgres.py` require
  `POLICY_TEST_DATABASE_URL` pointing to the isolated `bss_policy_test` database;
  each test uses/removes its own schema. They cover migrations, legacy adoption,
  duplicate protection, concurrent saves and capture.
- `docs/validate-exit-policies.py` runs real HTTP capture checks inside an API
  container after backup. It never changes the global mode, creates uniquely
  named test actions/clocks/events, and retires only its test clocks. Accepted
  test events remain for auditability; rejected exits generate no events.
