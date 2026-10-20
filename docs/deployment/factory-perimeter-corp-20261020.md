# CORP Factory Perimeter deployment, 2026-10-20

Target: `a414089787f68f0d72394557efebd33195fa20cb`, reconciled with corporate `6635652` on `deploy/factory-perimeter-corp-20261020`. The corporate Oracle 40-character device limit and ambiguous-send reconciliation protections are retained. No remote push.

## Operating command

From `/opt/BSSTimeCollection`, always include the release override:

```sh
docker compose -f docker-compose.yml -f docker-compose.issue2.yml -f docker-compose.perimeter-corp.yml up -d --no-deps --no-build api worker web
```

Do not recreate `db`: PostgreSQL 16 PGDATA uses an anonymous volume alongside the named volume. Both original mounts and the original DB container were preserved. `.env` and original Compose files are byte-identical to backup. Oracle and seed remain false. Factory settings table is empty, so perimeter stays disabled and legacy duplicate behavior is preserved. Existing terminal roles default to CELL/DEFAULT; existing assignments, provisioning hashes and sessions are unchanged.

## Corrections and checks

- Add the missing terminal role constraint so migration `0010` reverses correctly.
- Flush automatic cell EXIT before its referencing local perimeter event; both share a transaction, timestamp and correlation ID.
- Preserve entry device/structure/Oracle context snapshots during cascade, including when the structure has since become inactive.
- Protect bidirectional gate reads against presence toggling during cooldown; dedicated EXIT readers bypass cooldown while inside. A bidirectional physical exit requires cooldown expiry; use dedicated exit readers for barriers.
- Return duplicate feedback for repeated completed cell exits, preserve factory/role in clones, fail closed on unavailable external validators, translate terminal feedback in en/es/fr/pl.
- Update stale PostgreSQL migration expectation and add concurrency, rollback, snapshots, disabled legacy, clone and UI regressions.

Final image backend tests: **65 passed, 1 skipped** (optional external database-admin connectivity test). Frontend: **27 passed**, TypeScript/Vite build passed. PostgreSQL migration upgrade/downgrade preserved a legacy terminal; full production dump restored into an isolated database and upgraded successfully. HTTP E2E ran on replica API/web/worker only, using `0000-E2E-ONLY`: provisioning, KEYPAD/RFID/BOTH, entry guard, deduplication, cascade, timestamps/correlation, cell-only queue, disabled legacy capture passed. No real attendance events generated.

Production read-only validation: API readiness and web health return 200, API/web/db healthy; worker running and logs Oracle enabled=False. All legacy table fingerprints match before/after (terminal last-seen diagnostics and updated_at omitted to allow normal polling). Original **30 attendance records**, catalogue, terminal assignments, provisioning/session secrets, settings and Oracle attempts unchanged. Full `.env`/Compose comparison passed; DB container ID and both mounts match.

## Backup and offline images

Backup directory: `/opt/BSSTimeCollection-backups/perimeter-20261020T072051Z`, mode 700. Contains full application archive including Git and `.env`, PostgreSQL custom-format full dump, immediate pre-deploy dump, diagnostic baseline data export, container inspection, before/after fingerprints, and cached frontend dependencies. The custom-format dump was restored successfully. Pre-deployment image tags: `bsstimecollection-api:pre-perimeter-20261020`, `bsstimecollection-web:pre-perimeter-20261020`, `bsstimecollection-worker:pre-perimeter-20261020`.

The normal dependency build could not reach package registries. The release override uses `Dockerfile.corp-offline` files: unchanged deployed Python dependencies and existing frontend node_modules, with tests/build executed in Docker. To rebuild the frontend, restore the dependency archive temporarily:

```sh
cp /opt/BSSTimeCollection-backups/perimeter-20261020T072051Z/node_modules.tar.gz frontend/node_modules.tar.gz
docker compose -f docker-compose.yml -f docker-compose.issue2.yml -f docker-compose.perimeter-corp.yml build api web
rm frontend/node_modules.tar.gz
```

Only disposable validation containers/networks were added. They were stopped after verification; production volumes were neither deleted nor recreated. Physical RFID readers and barrier behavior require an operator's check before enabling the feature. Browser interaction with actual provisioned production terminals was intentionally avoided; frontend flow tests and replica HTTP tests cover software behavior.
