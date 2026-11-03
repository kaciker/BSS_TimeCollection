# Send one selected Oracle event

Automatic delivery stays disabled (`ORACLE_ENABLED=false`). The operator command below never scans or claims the PENDING queue; it selects only the supplied BSS event ID and uses the shared `OracleClient` and delivery audit path.

Run commands from the deployed API container or an equivalent environment with the mounted Oracle credentials and the same database configuration.

1. Inspect the event and confirm it is a CELL event with the intended identity, mappings, and current delivery status. Do not select `LOCAL_ONLY`, `SENT`, `SENDING`, or `UNKNOWN` events.
2. Preview the exact payload without writes or HTTP calls:

   ```sh
   python -m app.tools.oracle_send_event --event-id <uuid>
   ```

3. Compare the payload and request number with the inspected event. Explicitly confirm the exact request number to send:

   ```sh
   python -m app.tools.oracle_send_event --event-id <uuid> --confirm-request-number '<exact requestNumber>' --send
   ```

4. This command marks and sends that one selected event exactly once. It does not retry. A retryable result remains scheduled under the worker's normal policy; keep `ORACLE_ENABLED=false` until the queue has been deliberately reviewed.
5. Inspect the event's `TransmissionAttempt` row for the exact request payload, response, HTTP status, duration, classification flags, error, and Oracle IDs.
6. Verify the event status and stored `timeEventRequestId` / `timeEventId`.
7. Optionally reconcile a successful or ambiguous request with a read-only Oracle GET by request number or returned Oracle request ID.
8. Never replay `UNKNOWN` blindly. Reconcile it read-only first and handle any resend as a separate, explicitly reviewed operation.

Dry-run performs no POST, audit insert, or event update. The explicit send requires the request number to match exactly and refuses missing or invalid Oracle mappings before transmitting.
