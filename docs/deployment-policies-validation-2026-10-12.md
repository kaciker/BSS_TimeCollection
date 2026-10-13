# Policies / Same Terminal Exit — deployment validation

GitHub `main` was fast-forwarded from `d66c88a` to `5535e70`. The upstream
feature was reviewed commit-by-commit. The corrections were initially deployed locally and are included in the
13 October publication with the terminal policy editor and terminal clock.
Pre-existing sidebar CSS and notes are included; the original image ZIP is
retained locally. See [exit-policies.md](exit-policies.md) for the final behavior.

## Corrections

- Removed import-time DDL. Added Alembic `0008_exit_policies` and shared model
  metadata, foreign key/check constraints, unique global/terminal scopes and
  preservation/explicit validation of any pre-existing unversioned table.
- Replaced read-then-insert configuration saves with atomic upserts. PostgreSQL
  advisory transaction locks serialize state checks/capture for each badge.
  State/entry ordering is deterministic even when timestamps tie.
- Added work-cell editing in Policies, validation in both policy and terminal
  configuration APIs, preservation of unrelated Oracle attributes, accurate
  missing/different cell rejection messages, and responsive UI with save locking
  and success/error handling. Policies compare current terminal work-cell
  configuration, as the upstream feature specified.
- Corrected Alembic config interpolation for percent-encoded database URLs.
- No change to the global default Disabled, Oracle integration, existing
  terminal cells, existing action mappings, event snapshots or environment.

## Backup and isolated validation

Backup directory:
`/opt/backups/BSS_TimeCollection/20261012-exit-policies/`.
It contains verified custom-format PostgreSQL dumps both before updating and
immediately before the schema migration, row snapshots, repository bundle,
source/configuration archive, prior running API/web images and `.env` checksum.

A separate Docker network, PostgreSQL container and API/web candidate were used.
The real backup was restored into the isolated `bss_policy_test` database and
migrated successfully to 0008 before production. PostgreSQL regression tests
use dedicated schemas which are removed after each test.

Backend: **45 passed, no skipped tests**, including the optional PostgreSQL
concurrent activation check. One existing Starlette/httpx deprecation warning.
Frontend: TypeScript/Vite production build passed. `git diff --check` passed.

Coverage includes Disabled, same/different terminal, matching/different/missing
work cells, case-sensitive cells, global changes and override/inheritance,
policy rechecks after showing the exit menu, hierarchical exits, latest entry,
validated cell edits, unrelated attribute preservation, adoption of legacy
storage, duplicate legacy globals failing without data loss, concurrent global
and terminal saves, and eight simultaneous scans/final exits. Exactly one
entry/final exit is captured under concurrency; rejected exits create neither
TimeEvent nor TransmissionAttempt.

## Production checks

Deployment command:
`docker compose up -d --no-deps --wait --wait-timeout 120 api worker web`.
The PostgreSQL container and its existing volume were retained. Alembic reports
`0008_exit_policies`; web/API/DB health checks passed and worker is running with
Oracle disabled. Web `/healthz` and API `/api/v1/health/ready` return HTTP 200.

`docs/validate-exit-policies.py` ran real HTTP checks in both replica and
production. Eight cases cover Disabled, Same Terminal allowed/rejected, Same
Work Cell allowed/different/missing-origin/missing-exit, and inheritance of
Disabled. Production global policy was never changed. Accepted checks retained
16 test entry/exit events for auditability. Each rejection returned 409 with
operator guidance and left event/attempt counts unchanged: **zero rejected
Oracle queue events**. Two test clocks were retired after the checks.

Playwright exercised Policies in both candidate and production at 320×568,
390×844, 768×1024 and 1280×800. All four modes saved and cells persisted after
reload; other attributes remained intact. No JavaScript errors or horizontal
overflow. A dedicated inactive UI test terminal was retired afterwards.
[Desktop screenshot](policies-desktop-validation.png).

Row comparisons against the immediate predeployment backup confirm all 72
historical events, existing attempts, actions, assignments and original terminal
configuration are preserved. Final counts: 88 events, 0 attempts, 12 actions,
14 terminals (including 3 retired validation clocks), 69 assignments. Original
baseline: 72 events, 0 attempts, 10 actions, 11 terminals, 65 assignments.
Only normal runtime identity/diagnostic fields may evolve during live operation.
`.env` checksum is unchanged. Global resolves to Disabled with no persisted
policy overrides left from the validation. Temporary validation infrastructure
was removed after checks. No deployment blockers remain.

## Final UI and publication — 13 October

Policies now contains only the global default. Terminal overrides and cells are
in Terminals → Edit → Exit policy, saved atomically with terminal configuration.
The final suite passed 47 tests, including PostgreSQL/concurrency checks, and
browser save/inheritance/cancel checks passed at 320–1280 px on replica and
production. The terminal clock is centered and matches the keypad width in all
identification modes (up to 620 px), verified in 21 scenarios at 320–3200 px.
Clock confirmations use the returned capture timestamp. Build and deployment
health checks passed; no schema change followed 0008. These final changes and
project state are included in the 13 October main publication.
