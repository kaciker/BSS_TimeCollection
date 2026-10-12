# Terminal exit policies

Administration: `/admin/policies`.

Policy **Same Terminal Exit** supports:

- `DISABLED` (default): any active terminal may capture an exit.
- `SAME_TERMINAL`: exit terminal ID must equal the terminal ID of the last ENTER event.
- `SAME_WORK_CELL`: both terminals must have the same non-empty `work_cell` key in their existing `oracle_attributes` configuration. Missing configuration fails closed.

Global settings apply unless a terminal-specific override is selected. `INHERIT` removes the override.

Configuration endpoints:

- `GET /api/v1/admin/policies/same-terminal-exit`
- `PUT /api/v1/admin/policies/same-terminal-exit` with `{"mode":"DISABLED"}`
- `PUT /api/v1/admin/policies/same-terminal-exit/terminals/{code}` with `{"mode":"INHERIT"}`

Restrictions are enforced on both scan and exit capture. A rejected exit returns HTTP 409 and does not create or send an Oracle event. No attendance or payroll rules are implemented here.

The policy table is initialized idempotently on API startup. Before production rollout, validate database migration governance, permissions, concurrent configuration updates, and operator-facing error messages. No production deployment is performed by these repository changes.
