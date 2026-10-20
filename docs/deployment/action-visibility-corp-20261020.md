# Action visibility CORP deployment — 2026-10-20

Local deployed commit: ff32d3fca5ca3724c45ac4e231917624947ae061. Merge of GitHub target 7d280f6f20ece99b4f82daa750f6b3abab721ceb with corporate 6b00fa7. Preserves all 0d7d3e55 cascade/concurrency/snapshot/migration corrections, Oracle 40-character limits and unified perimeter administration styling. No push.

Resolved PerimeterPanel merge by retaining shared admin styling and integrating eligible EXIT selector (active, no required subactions, includes hidden). Fixed stale notices for role saves, duplicate notice clearing, mutual exclusion of success/errors and accessible selector label. Added hidden assigned-action/cascade and selector/notification regressions. Updated PostgreSQL migration head expectation.

Backup: /opt/BSSTimeCollection-backups/visibility-20261020T075537Z. Application tar includes .env and Git; PostgreSQL custom-format dump restored successfully into isolated bss_visibility_restore. SHA256 checksums and before/after fingerprints stored there. Existing action visibility defaults true; migration 0011_action_visibility upgrade/downgrade/upgrade validated in restored copy. Production only upgraded, no downgrade.

Tests on final API image: 70 passed, 1 optional external DB-admin test skipped. Frontend Docker tests: 29 passed; TypeScript/Vite build passed. PostgreSQL concurrency/cascade and rollback regressions passed. HTTP E2E against disposable replica only: hidden EXIT internal cascade, hidden action absent from terminal config and forbidden in direct operator submission, last visible exit protected, shared timestamp/correlation, RFID/BOTH/KEYPAD, perimeter guard/dedup/disabled legacy passed. No production scan was submitted.

Build/deploy uses existing docker-compose.yml + docker-compose.issue2.yml + docker-compose.perimeter-corp.yml, offline Dockerfiles and existing dependencies. API and worker use same rebuilt API image; web rebuilt. Only api/worker/web recreated; original db container and volume mounts preserved. Previous images tagged pre-visibility-20261020. .env and all Compose files compared byte-for-byte to backup. All legacy columns fingerprinted, including perimeter tables and terminal assignment/session hashes; terminal polling diagnostics omitted. No existing configuration edited. Perimeter remains disabled and ORACLE_ENABLED=false.

Physical reader/barrier tests remain manual before enabling perimeter. No remote publication. Historical CURRENT_STATE/MEMORY notes are working-tree changes.
