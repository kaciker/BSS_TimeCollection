# BSS Time Collection

BSS Time Collection is an **External Time Collection Device (TCD)** application designed to capture factory attendance events and reliably deliver them to Oracle HCM Time and Labor.

The application intentionally **does not implement Time & Attendance business logic**. It records facts; Oracle interprets them.

## Scope

The application provides:

- Terminal identity and configuration.
- RFID/badge identifier capture and manual keypad input.
- Configurable identification mode per terminal: `RFID`, `KEYPAD`, or `BOTH`.
- Configurable actions per terminal.
- Automatic entry registration when the last locally captured state is outside.
- Exit-reason selection when the last locally captured state is inside.
- Durable event storage in the BSS PostgreSQL database.
- Independent technical transmission history.
- Asynchronous Oracle REST delivery with retries.
- Conservative handling of ambiguous delivery timeouts to avoid blind duplicate retries.
- Oracle request/event identifiers stored when returned.
- Admin API and basic administration UI.
- Docker Compose deployment.

## Explicitly out of scope

The application does **not** manage:

- Employee master data or employee names.
- Shifts, schedules, calendars, worked hours, overtime or payroll.
- Oracle time cards.
- Missing-punch correction.
- Functional validation of attendance events.
- Approval workflows.
- Oracle business rules or IN/OUT pairing.

Oracle HCM Time and Labor remains the functional system of record.

## Worker state

A minimal state is derived only to simplify terminal UX:

- Last relevant event has `state_effect=ENTER` -> worker is considered `INSIDE` by the terminal UI.
- Last relevant event has `state_effect=EXIT` or no event exists -> worker is considered `OUTSIDE`.

This state is **not** an authoritative attendance status. It exists only so a worker does not need to choose IN or OUT manually.

## Authentication

Authentication is deliberately **not implemented in this version**. The application is currently open inside its trusted deployment boundary.

This is intentional because the final authentication model is pending a product decision: the module may be embedded in another authenticated application or receive its own authentication layer later. Keep authentication concerns outside the domain/event services when adding it.

## Architecture

```text
Terminal browser
   |
   | /api/v1/terminal/*
   v
FastAPI API -------- PostgreSQL
   |                     |
   |                     +-- time events
   |                     +-- transmission attempts
   |
Worker
   |
   | HTTPS / REST / JSON
   v
Oracle HCM Time and Labor
```

The web container is the only public entry point by default. It serves the React UI and proxies `/api` to FastAPI.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Open:

- Terminal: `http://localhost:8080/terminal/DEMO-01`
- Admin: `http://localhost:8080/admin`
- Health: `http://localhost:8080/api/v1/health/ready`

The default compose configuration seeds a demo terminal and actions. Disable this before controlled production rollout with `APP_SEED_DEFAULTS=false`.

## Oracle integration

Oracle delivery is disabled by default. Configure `.env` and set `ORACLE_ENABLED=true` only after the tenant endpoint, authentication method and supplier event mappings are validated with the Oracle team.

The adapter sends one local event per Oracle `timeEventRequests` request. This favors traceability and reconciliation over batching in the initial release.

See `docs/oracle-contract.md` for the payload contract and `docs/architecture.md` for design boundaries.
