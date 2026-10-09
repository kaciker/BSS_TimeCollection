# Terminal identity deployment validation — 9 October 2026

Deployment: Docker-Main, `/opt/BSS_TimeCollection`, local HTTP port 8092. Updated from `08808c0` to `544883e`, followed by the fixes described below.

## Backup and migration

Before changing configuration or the database, created a restricted backup at `/opt/backups/BSS_TimeCollection/20261009T204740Z-terminal-identity/`: original `.env`, Compose/proxy/Alembic/managed configuration, local runtime files, PostgreSQL custom-format dump and pre-migration table snapshots. The dump was successfully listed with `pg_restore`.

Applied `0002_terminal_identity_context` using `docker compose run --rm --no-deps api alembic upgrade head`. Reviewed the additive terminal columns and replacement event index against the actual database before migration. No database or persistent volume was recreated. API, worker and web were rebuilt/recreated; the original PostgreSQL container remained running.

Existing `.env` content was preserved, appending only `TERMINAL_COOKIE_SECURE=false` and `TERMINAL_SESSION_DAYS=365`. Oracle remained disabled throughout. HTTP uses a non-Secure cookie; HTTPS deployments must explicitly enable Secure.

## Issues corrected

- Reproduced concurrent reuse of an activation token: two out of eight concurrent HTTP requests returned success. Added a PostgreSQL row lock for activation and provisioning so token consumption and reprovisioning are serialized. Regression test runs five rounds of eight concurrent requests; each round requires exactly one 200 and seven 404 responses.
- The activation URL copy button assumed `navigator.clipboard` was available, which fails on local non-secure HTTP. Added a selected-input copy fallback, success feedback and readable errors. Verified the button reaches `Copied` on this HTTP deployment.

## Validation results

- Full suite: **15 passed**, including the opt-in concurrency test against an isolated PostgreSQL-backed API (`IDENTITY_TEST_BASE_URL`). Default suite: 14 passed, one integration test skipped until the isolated API is supplied. One dependency deprecation warning; no test failures.
- TypeScript/Vite production build and `docker compose config --quiet` succeeded.
- Alembic current revision equals head: `0002_terminal_identity_context`.
- Database, API and web health checks passed; worker running and explicitly logging `Oracle enabled=False`. Worker has no configured Docker health check.
- Administration create/edit saved all four extensible terminal attributes: Workshop, Project, Cell and Plant. Reporter ID type is terminal configuration.
- Test terminal: `TEST-PROVISION-20261009`; test badge: `99091020260001`. Dedicated English test entry/exit actions were added without changing existing actions.
- Browser activation via `/terminal/activate#TOKEN` succeeded, replaced the URL with `/terminal` and rejected token replay with 404. Cookie is HttpOnly, SameSite=Strict, Secure=false; JavaScript cannot read it. Reload and navigation back from administration retained the terminal identity.
- Reprovisioning invalidated the prior browser session (401); a fresh activation restored access. Changing User-Agent did not change identity. The legacy code-based config endpoint returned 404.
- UI entry and exit succeeded. PostgreSQL/API snapshots and the Oracle payload generator verified all four attributes and action-specific EventClass. The entry action overrode Cell; the exit retained terminal Cell. No real Oracle request was sent.
- Entry event: `201fcd95-f33e-4bbd-8cf9-bb9796139426`; exit event: `a011507f-0c58-44ce-b12b-556d76577417`. Both remain PENDING with no delivery attempt.
- Monitoring displayed both test events, full context in event details and OUTSIDE as the final card state.
- Retry tests returned 409 for UNKNOWN and REJECTED, preserving the required reconciliation boundary.
- Compared every original field of every pre-existing row against the database after migration and testing: **18 events, 0 transmission attempts, 1 terminal, 5 actions and 5 terminal/action assignments preserved**. Only explicitly named test records were added.

Local MyCodex/runtime files are excluded through `.git/info/exclude`; they were preserved and backed up rather than deleted. Temporary integration-test database and containers are removed after validation. Existing physical browsers must be explicitly provisioned from Administration; no identity is inferred from their URL, IP or User-Agent.
