# CORP deployment

`corp` is the operational branch for the CORP BSS Time Collection deployment.
It includes the application state from `main` plus the validated corporate
Docker configuration; do not merge deployment-only settings into `main`.
BSS captures attendance facts durably; Oracle HCM Time and Labor remains the
functional system of record.

## Local configuration and images

The local, untracked `.env` configures `WEB_PORT=8080`,
`APP_SEED_DEFAULTS=false` and `ORACLE_ENABLED=false`. Compose keeps the public
port configurable through `${WEB_PORT:-8080}`. Never commit `.env`, credentials,
deployment backups, database data or runtime artifacts.

Validated image tags:

- PostgreSQL: `postgres:16.4-alpine`.
- API/worker base: `python:3.12-slim`.
- Frontend build base: `node:22-bookworm-slim`.
- Frontend runtime: `nginx:alpine`.

Action/Sub-action definitions and visual keys are stored in PostgreSQL. The
seven action PNG files are local frontend static assets packaged in the web
image. `migration/actions-prod.json` is a configuration package, not an
automatic startup import; retain the existing database configuration.

## Build-only proxy

Compose passes `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, `http_proxy`,
`https_proxy` and `no_proxy` as build arguments inherited from the host shell.
Backend and frontend build-stage Dockerfiles declare corresponding `ARG`
variables. The host login shell supplies the corporate proxy
`http://10.42.252.16:3128` and corporate/private exclusions; `NO_PROXY` must also
cover localhost and Docker service names `api`, `worker`, `web`, `db`.
The current host exclusions cover corporate/private destinations and localhost;
append Docker service names in the build command without changing global
configuration. Use the configured login shell, including over non-login SSH:

```sh
bash -lc 'cd /opt/BSSTimeCollection &&
  export NO_PROXY="${NO_PROXY:+$NO_PROXY,}api,worker,web,db" &&
  export no_proxy="${no_proxy:+$no_proxy,}api,worker,web,db" &&
  docker compose build'
```

Do not put proxy variables in the project `.env`, Dockerfile `ENV`, or
API/worker/web runtime environments. Runtime containers have no proxy by
default. Do not modify global Docker daemon proxy settings or restart Docker;
other server applications must remain unaffected.

## PostgreSQL and terminal persistence

Preserve all existing PostgreSQL volumes. The validated PostgreSQL 16 layout
has the named `bsstimecollection_postgres_data` volume mounted at
`/var/lib/postgresql` and an existing anonymous volume mounted at the actual
`PGDATA=/var/lib/postgresql/data`. Both must be retained; the parent named
mount alone does not contain the live database. Do not change this layout
without a separate backed-up database migration.

Normal `docker compose build` and `docker compose up -d` recreation retain
existing volumes. Never use `docker compose down -v`, `docker volume rm`,
`docker compose up --renew-anon-volumes`, or destructive database commands.
Avoid `docker compose down`: after container removal, the anonymous live-data
volume is not automatically reattached by a subsequent `up`.

Terminal identity is the browser's HttpOnly/SameSite=Strict session cookie
plus its `session_token_hash` persisted in PostgreSQL. Normal rebuild/recreate
operations preserve provisioning when the existing database volumes and
browser cookie are retained. Reprovisioning deliberately revokes the previous
session; it is not part of routine deployment.

After an authorized deployment, check `docker compose ps`,
`http://127.0.0.1:8080/api/v1/health/ready` and `http://127.0.0.1:8080/`, verify
API/worker/web runtime proxy variables are empty, and compare terminal
provisioning and configuration against a read-only pre-deployment baseline.
