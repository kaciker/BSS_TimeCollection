# Factory Perimeter (Issue #3)

Optional factory-local UID presence tracking. Existing installations remain disabled. This module stores card identifiers only; it does not reconcile employee identity.

## Setup

1. Apply Alembic migration `0010_factory_perimeter` after backing up the database.
2. In **Admin → Factory Perimeter**, choose the factory code (default `DEFAULT`), configure an existing active leaf EXIT action (e.g. `STOP`) as the automatic cell exit reason, then enable the module.
3. Assign gate terminals a role: `PERIMETER_ENTER`, `PERIMETER_EXIT`, or `PERIMETER_BOTH`. Existing terminals remain `CELL`. Assign all related terminals the same factory code.
4. Test a badge at the gate before the cell. A cell entry without gate presence is rejected.
5. A gate EXIT while the badge is still in a cell records a normal cell EXIT (queued for Oracle) and a separate factory EXIT (never queued for Oracle) in one database transaction. The factory EXIT contains a correlation ID and links to the generated cell event.

## Policies

- `enabled`: factory presence required for cell entry; default false.
- `badge_source`: `OPEN` accepts any UID presented at the gate. `EXTERNAL` is reserved and cannot be enabled until a validator is implemented.
- `dedup_enabled` and `dedup_seconds`: per-factory repeat scan policy; defaults true and 5 seconds once a factory is explicitly configured. Existing installations without a configuration retain legacy capture behavior.
- Physical gate EXIT is never blocked by the duplicate-scan policy. Use dedicated entrance and exit readers where physical direction is known.
- `auto_exit_action_code`: existing active EXIT action used to label automatic cell exits. Use a distinct catalog action for reporting/Oracle mapping if desired; do not use an action requiring subactions.

## Integration boundaries

The factory presence log is local, not an Oracle Time Collection event. Only cell events enter the Oracle delivery worker. No external badge database, third-party perimeter protocol, HR feed, or personal record is connected in this version. Integrate these through dedicated adapters after defining the plant-specific interface.

## Limitations / validation before CORP

This branch must pass backend and frontend CI, database migration checks, physical reader tests and concurrent gate/cell scenarios before production deployment. The existing administration API has no authentication; keep it behind the existing trusted network/gateway and do not expose publicly. A factory exit should be considered physical access control: its terminal must be secured against unauthorised access.
