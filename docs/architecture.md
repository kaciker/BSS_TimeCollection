# Architecture

## Design rule

**BSS Time Collection records and delivers facts. Oracle HCM Time and Labor interprets those facts.**

The application owns capture reliability, terminal UX, local auditability and technical delivery state. Oracle owns employee identity resolution, schedules, business rules, validation, exceptions, IN/OUT matching, time cards and payroll integration.

## Components

### Web terminal

The React terminal UI captures a badge identifier through the enabled identification method. The initial implementation supports the on-screen keypad. RFID integration can use the same API contract and is intentionally isolated from attendance logic.

### FastAPI API

The API owns terminal configuration, action configuration, event creation and derived interaction state.

### PostgreSQL

The database stores immutable event facts plus separate technical delivery attempts. Event snapshots retain the terminal device ID and supplier event code that existed at capture time so later configuration changes cannot rewrite history.

### Delivery worker

The worker independently sends pending events to Oracle. Oracle unavailability never changes an already captured event.

Network failures known to have occurred before request delivery are retried. Ambiguous read/write timeouts are marked `UNKNOWN` rather than blindly replayed, because the remote system may already have persisted the event.

## Interaction state

The terminal derives a minimal state from the latest locally captured event for a reporter:

```text
ENTER -> INSIDE
EXIT  -> OUTSIDE
none  -> OUTSIDE
```

When outside, scanning the badge automatically records the terminal's configured entry action. When inside, scanning returns the configured exit actions so the worker selects a reason.

This state is a UX convenience only and must never be used as authoritative worked-time data.

## Authentication boundary

Version 0.1 has no authentication. Do not add domain dependencies on a particular identity provider. A future gateway/middleware can protect admin and terminal routes, or the module can be embedded in another application.
