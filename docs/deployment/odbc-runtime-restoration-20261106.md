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

## Build and deployment gate

The only configured builder is the production Docker daemon; it was not used.
No separate authorized builder was found, and GitHub Actions was not authorized
as the isolated release builder. Candidate build and deployment remain pending.

Before deployment, record API/worker container and image IDs, effective Compose
settings, health and restart counts, and verify the Oracle transmission queue
is idle. Back up deployment files and retain the old images for rollback.
Replace only API and worker. Preserve database/web services, credentials,
volumes, Oracle controls, RFID canonicalization, factory mappings and external
presence behavior. Verify both services use the same candidate image and check
`import pyodbc`, `pyodbc.drivers()`, `odbcinst`, and `libodbc.so.2`. Perform an
approved read-only ARGANDA connection and synchronization check without Oracle
transmission. On failure restore recorded image references and Compose files,
recreate only API and worker, then verify health and preserved state. Record
previous image IDs and explicit deployment approval in the release record.
