# SQL Server ODBC runtime restoration — 2026-11-06

## Cause

The production API and worker image histories show Python `pyodbc` in a staged
site-packages overlay but no unixODBC or Microsoft driver installation layer.
This reproduces the missing `libodbc.so.2` import failure. The standard backend
Dockerfile omitted ODBC, while CORP-specific builds depended on a local base
tag carrying ODBC, allowing newer recovery paths to omit the system runtime.

## Source correction

Both corporate offline Dockerfiles now install the staged Debian packages and
Python wheel, verify all entries in
`backend/odbc-packages/MANIFEST.txt`, refresh the loader, register Microsoft
ODBC Driver 18, and check `libodbc.so.2`, `odbcinst`, `import pyodbc`, and
`pyodbc.drivers()`. API and worker use the same backend recipe and recovery
image tag. Package binaries remain local, gitignored build inputs; stage all
20 files from the verified offline bundle before building.

## Validation

- Backend suite: 341 passed, 8 skipped.
- ODBC regression tests: 3 passed.
- All 20 staged package hashes passed.
- A network-disabled temporary container installed the package bundle;
  `pyodbc` 5.2.0 imported, `odbcinst` listed Driver 18, and `libodbc.so.2`
  resolved.
- No SQL Server connection, synchronization, or Oracle transmission ran.

## Production recovery verified — 2026-11-06

PR #48 was merged into GitHub `main` as squash commit
`12aaee8b835ec6c959a1140b13ad9547d65d3669`. The production API and worker
now use image `bsstimecollection-api:odbc-oracle-safe-20261106`
(`sha256:aa142b948cd813cedd594cd4f8715ab2a91015121476d6d796aa0f007a2340b1`).

Production verification reported for this recovery:

- Microsoft ODBC Driver 18 is available.
- `pyodbc` 5.2.0 is operational.
- The API is healthy.

The source recovery in this release pins the offline bundle checksums in Git
and installs the same ODBC runtime through the corporate offline and recovery
Dockerfiles. The 20 package binaries remain staged build inputs and are
gitignored; rebuilds require staging the verified bundle described above.
The production image tag and digest identify the recovered runtime.

For any later API/worker replacement, retain the deployment safeguards in this
record: preserve current Oracle transmission controls, database/web services,
credentials, volumes and factory/RFID configuration; use a verified backup
when database changes are involved; and validate without creating production
time events.
