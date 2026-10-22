# Arganda SECURITY_DB validation — 2026-10-22

## CORP runtime findings

The API image is `bsstimecollection-api:admin-auth-ba7923d`, labeled source revision `22ce771ce5f4f635e20c858c6242643230ae7c29`. It was created from `docker-compose.yml` plus `/tmp/bss-admin-auth-deploy.yml`; the corporate perimeter override was not applied. The API has no mounts and no `PERIMETER_*` environment values. The host credential file exists root-owned with mode `0600`, but is absent at `/run/secrets/perimeter_sqlserver.json` in the API. The active web image is separately labeled `988a926+i18n` and uses its own temporary compose override.

Inside the API, Python 3.12, `pyodbc`, and ODBC Driver 18 are present. A TCP connection to `10.33.157.67:1433` succeeds. The adapter therefore returns `ERROR` because credentials are unavailable to the container. SQL login and the presence query were not attempted. The only known login was previously verified to have DML privileges and is not eligible for production read-only use.

PostgreSQL currently reports ARGANDA `enabled=true`, `badge_source=EXTERNAL`; DEFAULT remains disabled with OPEN. `ORACLE_ENABLED=false`. No production setting or data was changed during this validation.

## Code and local verification

The adapter now classifies internal connector failures without exposing driver messages or credentials. Protected admin routes report connector status, run a read-only `SELECT 1`, and test a badge using the existing presence query without writing BSS data. The Perimeter panel displays the external status and test controls, and suppresses local BSS presence/movement lists while EXTERNAL is selected.

- Backend: 83 passed, 7 skipped.
- Frontend: 43 passed; production build passed.
- Adapter-specific endpoint test confirms a badge test creates neither `TimeEvent` nor `FactoryPerimeterEvent`.

## Deployment gate

Do not deploy/attach the current host credential file or run SQL checks until a dedicated account is verified SELECT-only. After that, apply the corporate perimeter Compose override to the API, rebuild/recreate only API (and web for the UI), verify Oracle remains disabled, then use connector status/check and test a previously approved known badge. Do not record a terminal scan as part of this validation. No SQL connection or badge lookup against production was made in this validation.
