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

## Administration monitoring

Open `/admin` for the administration workspace. Sidebar navigation separates operations from configuration; each section has its own URL. Monitoring pages:

- **Badge status**: latest local ENTER/EXIT state per badge, defaulting to INSIDE. Filter first by clock, then badge and local state. The clock is the terminal of the latest event; state is computed across all terminals before filtering, so an exit on another clock supersedes an earlier entry. Only badges with captured relevant events appear. This is a local interaction state, not Oracle-validated attendance.
- **Event logs**: persisted events filtered by clock, badge substring, delivery status and event timestamp range. Each event opens a complete detail view.
- **Transmission logs**: individual recorded delivery attempts filtered by clock, badge substring and attempt result. Details show endpoint, timing, HTTP status, error and the exact persisted request/response JSON for each attempt.

Views use server-side filters and pagination (50 rows), manual refresh and automatic refresh every 15 seconds. Date filters/display use the browser's local timezone. Badge identifiers remain strings, including leading zeros. Card history opens `/admin/events` with badge and clock filters in the URL and uses the same badge substring search.

The event inspector distinguishes the current Oracle payload preview from actual historical transmissions. The preview omits `requestTimestamp`, which is generated only at send time, and uses the current `sourceId`. Actual attempt payloads are read from the database. No attempts means no recorded Oracle transmission; `PENDING` must not be displayed as sent. `SENT` indicates transport acceptance, not downstream business validation. Monitoring endpoints are read-only and do not replay or modify events.

API endpoints: `/api/v1/admin/monitoring/cards`, `/events`, `/attempts` and `/events/{event_id}`. List responses include `items` and filtered `total`; `offset`/`limit` provide pagination.

The current UI, API messages and event records use English. Multilingual menus may be considered later; event records remain in English.


## Terminal and action configuration

The administration sidebar separates five pages: `/admin/cards`, `/admin/events`, `/admin/attempts`, `/admin/terminals` and `/admin/actions`. Lists provide search/filter controls; configuration changes use dedicated dialogs with explicit Save/Cancel, visible errors and success feedback. All product text and event labels use English.

Terminal creation and editing include name, unique Oracle device ID, identification method, availability and action assignments in one transaction. Terminal codes are stable. An active terminal requires exactly one active ENTER action and at least one active EXIT action; incomplete configurations can be saved as inactive drafts. Duplicate codes/device IDs return readable HTTP 409 errors.

Actions can be created and edited through the UI: English label, supplier event code, ENTER/EXIT effect, reporter ID type, display order, availability and optional Oracle attributes as a JSON object. Action codes are stable. Supplier event codes must be unique. Changes that would remove the required entry/exit actions of an active terminal are rejected. Reassign or deactivate the affected terminal first. Configuration changes apply to future captures; existing events retain their recorded snapshots.

API: `POST /api/v1/admin/terminals`, `PUT /api/v1/admin/terminals/{terminal_code}`, `POST /api/v1/admin/actions` and `PUT /api/v1/admin/actions/{action_code}`. Terminal payloads include `action_codes` and `active`; action payloads include `active`. PUT accepts the complete settings (stable code is determined by the URL). Demo seeding assigns defaults only when initially creating the demo terminal and no longer replaces saved assignments on startup.
