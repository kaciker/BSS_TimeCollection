# Arganda external perimeter — staging integration

The Arganda external adapter reads SQL Server `SECURITY_DB` using a badge-only lookup. It does not create fictitious gate events, change external data, or send gate movements to Oracle.

- Source: latest `acc_transaction` with `acc_zone_code IN (1,2)`, ordered by `event_time DESC, log_id DESC`.
- Badge conversion: validated 32-bit decimal reader number with reversed bytes.
- Presence: `2 = INSIDE`, `1 = OUTSIDE`; INSIDE older than 12 hours is `STALE`.
- Unknown, stale and connection errors fail closed for **new cell entry**. Existing cell exits remain possible.
- The external integration is **not** a push notification system; it does not automatically create a cell exit when someone passes the physical gate. This requires a separately approved reconciler.
- Factory selection: only `ARGANDA` can select `EXTERNAL`. Other factories retain `OPEN`.

## Deployment prerequisites (Codex CORP)

1. Inspect the actual root-only `/opt/BSSTimeCollection/sql/credentials.json` schema and create a separate, restricted, structured JSON file for the adapter with keys `server`, `database`, `username`, `password`. Do not change the original discovery script. Do not commit the credentials.
2. Mount that file read-only into the API container at `/run/secrets/perimeter_sqlserver.json` using a **corporate-only** Compose override. The container must have `pyodbc`, unixODBC and **ODBC Driver 18 for SQL Server** installed. The generic image intentionally does not assume that the corporate driver is available.
3. Ensure the container can reach SQL Server `10.33.157.67:1433`. The host-only discovery test is not sufficient.
4. Test with known non-sensitive badges; verify byte conversion, zone values, timezone and last-event ordering. The server currently requires `Encrypt=yes;TrustServerCertificate=yes` due to a weak certificate: this is a security exception, not verified server identity.
5. Keep factory `ARGANDA` **disabled**, `ORACLE_ENABLED=false`, and preserve all production records. Perform dry-run read-only lookups and end-to-end replica tests before asking for approval to enable EXTERNAL.

## Runtime environment

`PERIMETER_SQLSERVER_CREDENTIALS_FILE=/run/secrets/perimeter_sqlserver.json`

`PERIMETER_EXTERNAL_MAX_AGE_HOURS=12`

This implementation uses a **global 12-hour limit** for the Arganda-only connector. Additional factories require their own provider configuration and independent policy.

**Important:** existing factory presence screens show local BSS gate events, not the external SQL Server's live presence population. Do not interpret that list as Arganda's authoritative headcount.
