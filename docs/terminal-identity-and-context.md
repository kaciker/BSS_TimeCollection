# Terminal identity and Oracle context

## Browser-only terminal binding

BSS Time Collection does not attempt to fingerprint PC hardware. A terminal is a logical factory workstation provisioned to one browser.

1. Administration creates or reprovisions a terminal and generates a cryptographically random one-time activation token.
2. The activation URL uses a URL fragment: `/terminal/activate#<token>`. Fragments are not sent in HTTP request paths, which avoids exposing the activation secret in normal reverse-proxy access logs.
3. The SPA posts the token once to `/api/v1/terminal/activate`.
4. The backend consumes the activation token, creates a new random terminal session, stores only its SHA-256 hash and sets the plaintext session token in an `HttpOnly`, `SameSite=Strict` cookie.
5. The SPA immediately replaces the browser URL with `/terminal`, so the activation token disappears from the address bar/history entry.
6. Runtime APIs resolve terminal identity only from the browser session. The worker cannot select or change the terminal code in the URL.

Reprovisioning generates a fresh activation token and revokes the previous browser session. IP address and user agent are retained only as last-seen diagnostic context; they are not terminal identity.

For HTTPS production deployments set `TERMINAL_COOKIE_SECURE=true`.

## Application-managed terminal code

The normal Administration flow does not ask an operator to invent a terminal code. The backend allocates stable codes in the form `T0001`, `T0002`, and so on. Codes are immutable and logically deleted terminals keep their code reserved, so historical identifiers are never reused.

Cloning also allocates a fresh application-managed terminal code. The Oracle device ID remains a separate integration identifier and can be reviewed or changed before provisioning the cloned browser.

The create API still accepts an explicit `code` for migration and automated-test compatibility. Normal UI creation omits it and delegates allocation to the application.

## Global reporter ID type

`reporterIdType` describes the meaning of the worker identifier sent to Oracle, not how the identifier was captured. It is therefore global Oracle integration configuration rather than a per-terminal setting.

The backend setting is `ORACLE_REPORTER_ID_TYPE`, defaulting to `BADGE`. RFID and keypad remain capture methods; both can produce a reporter ID whose Oracle type is `BADGE`. New event snapshots use the global value at capture time.

Administration Settings exposes the effective reporter ID type, Oracle source ID and delivery enabled/disabled state as read-only integration information.

## Structured Oracle terminal context

Administration presents the standard terminal context as structured fields:

- `Plant`
- `Workshop`
- `Cell`
- `Project`

The UI builds the `oracle_attributes` object automatically when the terminal is saved. Administrators do not need to construct the normal context as JSON. A collapsed **Advanced Oracle attributes** editor remains available only for additional, non-standard Oracle attributes.

The Same Work Cell exit policy uses the separate local `work_cell` value. It is stored with terminal configuration for backward compatibility but is removed when a new event snapshot is built, so it is not emitted as an Oracle `timeEventAttribute`. Oracle `Cell` and local policy `work_cell` are intentionally distinct concepts.

On capture, BSS copies the structured terminal Oracle attributes into the immutable event snapshot and then overlays any action-specific Oracle attributes. The resulting snapshot is what the Oracle adapter serializes as `timeEventAttributes`.

Later edits to Plant, Workshop, Cell, Project or custom attributes affect only future captures. Historical events and already-recorded transmission attempts remain unchanged.

## Delivery safety

`UNKNOWN` events are not manually replayable until they have been reconciled, because Oracle may already have accepted the original request. `REJECTED` events are also blocked from blind replay; mapping or source data must be corrected deliberately first. `SENT` and in-flight `SENDING` events remain non-replayable.

## Concurrent activation and local HTTP

Activation locks the matching terminal row until the token has been consumed, so simultaneous requests cannot each create a valid session. Reprovisioning locks the same row before replacing activation/session hashes.

The Administration copy button supports local HTTP where the Clipboard API is unavailable, with a selected-input fallback and visible copy feedback. This does not change the HttpOnly session boundary.

PostgreSQL-backed concurrency regression test (run only against an isolated test API):

```bash
IDENTITY_TEST_BASE_URL=http://127.0.0.1:8000 pytest -q
```

See [deployment validation](deployment-validation-2026-10-09.md) for migration, preservation and browser evidence.
