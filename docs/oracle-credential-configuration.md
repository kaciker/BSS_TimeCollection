# Oracle credential configuration

Oracle credentials are configured in the authenticated Admin Settings page. Basic mode stores a username and password; Bearer mode stores a token; None stores no active authentication method. A blank secret input preserves its previous value. Clearing a secret requires the explicit checkbox.

The API writes credentials atomically to `/opt/BSSTimeCollection-secrets/oracle/oracle_credentials.json` on the host by default. The host directory is mode `0700`, and the file is mode `0600`. The API mounts the directory read/write; the worker mounts the same directory read-only. The host directory can be changed with `ORACLE_CREDENTIALS_HOST_DIR`; the in-container path is `/run/secrets/oracle/oracle_credentials.json`.

When the file is absent, the existing `ORACLE_AUTH_MODE`, `ORACLE_USERNAME`, `ORACLE_PASSWORD`, and `ORACLE_BEARER_TOKEN` environment variables remain the fallback. Once the file exists, its values take precedence. Do not place the credential file in the repository or include it in diagnostics/backups intended for source control.

Host connectivity checks only request the Oracle base URL without credentials. Authentication validation uses streamed `GET /hcmRestApi/resources/11.13.18.05/timeEventRequests/describe`, closes the response without consuming metadata, disables redirects, and never submits a time event. The configured DEV2 tenant returned HTTP 200 to this authenticated metadata request on 2026-10-30; this confirms metadata read permission only, not event-create permission. Credential configuration and validation do not enable delivery; CORP keeps `ORACLE_ENABLED=false`.

## Deployment and rollback

Before deployment, create and verify a timestamped backup of the application source/runtime configuration and database dump. Preserve `.env`, credential files, database and perimeter credential mounts, and PostgreSQL volumes. Recreate only the application services whose images changed (`api`, `worker`, and/or `web`) with the existing CORP Compose file list plus `docker-compose.oracle-hrpath.yml`; do not use `down` or recreate the database. Confirm health, migrations, and `ORACLE_ENABLED=false` afterward. Rollback by recreating only the affected application service(s) with the previously pinned image tags recorded in the backup's container manifest. Never restore or replace the database volume for an application-only rollback. The 2026-10-30 authentication validation used API and web only; the worker, database, and volumes were preserved.
