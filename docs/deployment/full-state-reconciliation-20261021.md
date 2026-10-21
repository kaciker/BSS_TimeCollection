# Full state reconciliation — 2026-10-21

Reference: corporate runtime on Titan APPS, checked read-only on 2026-10-21.

## Functional source consolidation

The release candidate is based on corporate checkpoint `988a9261fdff87dc70505691bf875e42aadc69a9`, which descends from deployed-hardening commit `96ddb8b` and connector safeguards at `22ce771`. It preserves corporate API/authentication changes, deployed ODBC runtime metadata, and adds the current localized administration/terminal UI with the EXTERNAL presence safeguards retained. It excludes operational metrics work, which is not deployed. Its separately committed checkpoint `7a33fc4` is preserved in draft PR #8, based on PR #6; review it independently.

GitHub `main` was `6cb48bdb7dcbe9151eb66e9dc849a7f33cdb34cb`; local `main` is `2ecc136641820be0bfd27e55c4517ebb9d2e5665`. They differ by commit ancestry (local is ahead 1/behind 2) but have the same tree. The original workspace keeps 22 tracked files modified (state/history notes and UI/localization changes); the localized release UI is also present in PR #6, so preserve those workspace edits for comparison before cleanup. The working tree has four untracked groups: `.backups/`, `.worktrees/`, `sql/`, and `alidate_sqlserver_readonly.py`. Draft PR #6 started from `c4e55b2`; the release file set and state correction are published on its head. Corporate follow-up commits after `c4e55b2` include connector corrections, offline ODBC packaging, secret mount and image provenance. The checkpoint line also contains temporary admin authentication and a reproducible frontend build.

## Runtime compared with Git

API image `bsstimecollection-api:admin-auth-ba7923d`, source label `22ce771`; API source hashes for admin auth, SQL Server connector and ODBC manifest match the corporate source tree. It contains pyodbc and Driver 18. Web image `bsstimecollection-web:admin-auth-react-dedupe-20261021`, source label `10df7ce`, built from `.worktrees/arganda-external` with temporary Compose overlays; its JavaScript bundle predates current localization edits. Worker image remains `bsstimecollection-api:perimeter-corp-20261020`, label `a414089+corp-corrections`, so it has no connector-specific worker changes. PostgreSQL 16.4 uses `bsstimecollection_postgres_data` and the original anonymous PGDATA volume; Alembic remains `0011_action_visibility`. `ORACLE_ENABLED=false`, `APP_SEED_DEFAULTS=false`, temporary admin authentication enabled. This reconciliation did not change containers, schema, volume or database state.

## Corporate overlay and sensitive local files

Runtime Compose uses `docker-compose.yml`, `docker-compose.issue2.yml`, `docker-compose.perimeter-corp.yml` plus `/tmp/bss-admin-auth-deploy.yml` and `/tmp/bss-admin-react-dedupe.yml`. There are no application bind mounts. The original workspace reports 37 ignored entries: environment files/backups, local deployment/configuration files, credentials, personal CSV extracts, Python caches, frontend `node_modules`/`dist`, and backup files. Keep `.env`, SQL Server JSON credentials/configuration, personal CSV extracts, PostgreSQL backups and deployment archives out of GitHub. `alidate_sqlserver_readonly.py` is a local helper and was not included. The local SQL credential/configuration and personal CSV files remain ignored; no credential, CSV, dump or backup was published. The tested SECURITY_DB login has DML privileges, so it is not suitable for read-only production use; EXTERNAL remains disabled and OPEN.

## Unpublished operational metrics

The separate `phase2c/release-candidate` branch has checkpoint `7a33fc4` for `0012_operational_metrics`, singleton worker telemetry, an authenticated aggregate endpoint and an Nginx deny rule. It is not in the running images or database. It is preserved for independent review in draft PR #8, with PR #6 as base; do not apply its migration as part of this reconciliation.
