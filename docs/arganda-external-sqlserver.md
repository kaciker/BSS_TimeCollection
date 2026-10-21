# Arganda external perimeter — staging integration

The Arganda external adapter reads SQL Server `SECURITY_DB` using a badge-only lookup. It does not create fictitious gate events, change external data, or send gate movements to Oracle.

- Source: latest `acc_transaction` with `acc_zone_code IN (1,2)`, ordered by `event_time DESC, log_id DESC`.
- Badge conversion: validated 32-bit decimal reader number with reversed bytes.
- Presence: `2 = INSIDE`, `1 = OUTSIDE`; INSIDE older than 12 hours is `STALE`.
- Unknown, stale and connection errors fail closed for **new cell entry**. Existing cell exits remain possible.
- The external integration is **not** a push notification system; it does not automatically create a cell exit when someone passes the physical gate. This requires a separately approved reconciler.
- Factory selection: only `ARGANDA` can select `EXTERNAL`. Other factories retain `OPEN`.
- `acc_zone_code` is stored as `nvarchar`; the adapter normalizes returned `"1"`/`"2"` values before applying state rules.
- SQL Server returns `event_time` as timezone-naive `datetime`. The adapter interprets it in configured `EVENT_TIMEZONE` (`Europe/Madrid` in CORP); verify this with the plant because SQL Server does not attach a timezone to the column.

## Deployment prerequisites (Codex CORP)

1. Inspect the actual root-only `/opt/BSSTimeCollection/sql/credentials.json` schema and create a separate, restricted, structured JSON file for the adapter with keys `server`, `database`, `username`, `password`. Do not change the original discovery script. Do not commit the credentials.
2. Verify that the login is database read-only before use. Mount that file read-only into the API container at `/run/secrets/perimeter_sqlserver.json` using a **corporate-only** Compose override. The container must have `pyodbc`, unixODBC and **ODBC Driver 18 for SQL Server** installed. The generic image intentionally does not assume that the corporate driver is available.
3. Ensure the container can reach SQL Server `10.33.157.67:1433`. The host-only discovery test is not sufficient.
4. Test with known non-sensitive badges; verify byte conversion, zone values, timezone and last-event ordering. The server currently requires `Encrypt=yes;TrustServerCertificate=yes` due to a weak certificate: this is a security exception, not verified server identity. Revisit certificate validation when the SQL Server certificate chain can be corrected.
5. Keep factory `ARGANDA` **disabled**, `ORACLE_ENABLED=false`, and preserve all production records. Perform dry-run read-only lookups and end-to-end replica tests before asking for approval to enable EXTERNAL.

## Runtime environment

`PERIMETER_SQLSERVER_CREDENTIALS_FILE=/run/secrets/perimeter_sqlserver.json`

`PERIMETER_EXTERNAL_MAX_AGE_HOURS=12`

This implementation uses a **global 12-hour limit** for the Arganda-only connector. Additional factories require their own provider configuration and independent policy.

**Important:** existing factory presence screens show local BSS gate events, not the external SQL Server's live presence population. When `EXTERNAL` is selected, the administration panel suppresses the local population and movement list because they are not authoritative.


## Corporate offline ODBC image

The CORP API image uses Debian 13 (trixie), amd64, and CPython 3.12. The corporate offline Dockerfile installs unixODBC and Microsoft ODBC Driver 18 from the official Debian 13 and Microsoft Debian 13 binary packages staged in `backend/odbc-packages/`; `MANIFEST.txt` pins SHA-256 for every package and the CPython 3.12 pyodbc wheel. The package bundle is generated from official signed repository metadata and its file SHA-256 values are pinned in `MANIFEST.txt`; package binaries are deployment inputs kept out of Git and are staged from official repositories before building. No host libraries are copied into the image. The build verifies hashes, registers Driver 18 with `odbcinst`, and checks `pyodbc.drivers()` before copying application code. Never add credentials to this bundle or image layers.

The deployment override mounts `/opt/BSSTimeCollection/sql/perimeter_sqlserver.json` read-only into the API only. Its root-only source file is excluded locally from Git. Driver 18 encrypts connections; `TrustServerCertificate=yes` remains a documented certificate-validation exception.


Production deployment 2026-10-21: deployed local commit `24efc8c` with Oracle disabled and ARGANDA/DEFAULT disabled in `OPEN`. The `SecurityDB_Reader` credential was validated as SELECT-only on the four required tables and mounted read-only in API. It is the same password shared in the support conversation, so rotate it before operationally enabling `EXTERNAL`.
