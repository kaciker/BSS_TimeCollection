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

## Configurable Oracle terminal context

Each terminal owns an extensible `oracle_attributes` JSON object. Example:

```json
{
  "Workshop": "Extrusion",
  "Project": "P42",
  "Cell": "EX07",
  "Plant": "Debica"
}
```

These values are editable in Administration. On capture, BSS copies the terminal attributes into the immutable event snapshot and then overlays any action-specific Oracle attributes. The resulting snapshot is what the Oracle adapter serializes as `timeEventAttributes`.

This means later edits to Workshop, Project, Cell or any future field affect only future captures. Historical events and already-recorded transmission attempts remain unchanged.

`reporterIdType` is terminal/integration configuration, not an action property. The event stores its resolved value at capture time.

## Delivery safety

`UNKNOWN` events are not manually replayable until they have been reconciled, because Oracle may already have accepted the original request. `REJECTED` events are also blocked from blind replay; mapping or source data must be corrected deliberately first. `SENT` and in-flight `SENDING` events remain non-replayable.
