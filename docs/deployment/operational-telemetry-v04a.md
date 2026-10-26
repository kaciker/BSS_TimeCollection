# v0.4A operational telemetry deployment

## Release state

This release adds the protected contract `GET /api/v1/health/operational` (version 1). It reports only aggregate event and transmission counts, aggregate perimeter activity, database snapshot time and bounded worker timestamps. It never serializes event rows, IDs, employee/badge values, payloads, endpoints or free-text errors. Oracle remains controlled by `ORACLE_ENABLED`; when disabled, Oracle and worker processing report `DISABLED` while local queue and perimeter aggregates remain visible.

The API checks `Authorization: Bearer <token>` using constant-time comparison and requires a token of at least 32 characters. Configure the same high-entropy value as `OPERATIONAL_METRICS_TOKEN` in Time Collection and `TIMECOLLECTION_OPERATIONAL_TOKEN` in Health Intelligence's protected environment. The exact Nginx path returns 404, so only trusted internal services that can reach `api:8000` directly can use this endpoint. Do not publish the API port or expose the route through a public proxy.

The worker remains a single Compose service. It heartbeats every 10 seconds, including with Oracle disabled; a successful queue cycle timestamp advances after a completed claim poll; and a successful delivery timestamp advances after the SENT result transaction commits. External perimeter replication and reconciliation continue on their existing schedule independently of Oracle state.

## Deploy after explicit production approval

1. Confirm the Health Intelligence service is attached to the same private Docker network as Time Collection API, or arrange an equivalently private trusted service path. Set matching 32+ character secrets in each service's secret store; do not use a URL parameter or commit them.
2. Verify `ORACLE_ENABLED=false`, `WEB_PORT` remains bound as currently configured, and the worker is configured as one replica.
3. Preserve the current Compose/database volumes and take the normal verified CORP backup. Do not run `down`, remove/renew volumes or recreate PostgreSQL.
4. From `/opt/BSSTimeCollection`, deploy only the app and worker source/images plus web Nginx configuration with `docker compose build api worker web` followed by `docker compose up -d --no-deps api worker web`. This does not migrate the database because its current Alembic revision is already `0014_terminal_exit_menu_timeout`, which descends from `0012_operational_metrics`.
5. Verify API and worker health, unchanged Oracle-disabled configuration, Nginx 404 at `/api/v1/health/operational`, authenticated internal endpoint HTTP 200 with `contract_version=1`, no-cache headers and aggregate-only response, and Health Intelligence coverage. Never generate test events or call Oracle transmission paths.

## Rollback

Use the verified pre-release source/image backups and restore only Time Collection API, worker, and web code/configuration. Recreate those services with `--no-deps`; retain the PostgreSQL containers and every existing volume. No schema downgrade is needed or recommended. Remove the matching service tokens from both services only if telemetry access is being retired. Keep Health Intelligence on its existing build if the Time Collection endpoint becomes unavailable; its adapter reports unsupported/unavailable metrics as unknown.

## Current evidence and remaining approval

CORP read-only inspection on 2026-10-26 returned database revision `0014_terminal_exit_menu_timeout`; Alembic's unique source head is the same revision. No migration is required. This source release and its test suite have not changed or restarted any CORP service, image, database or volume. Production source/image deployment, secret configuration, network attachment changes and service recreation still require explicit approval.
