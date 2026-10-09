# Oracle Time Event Contract

The Oracle adapter targets the Oracle HCM Time and Labor `timeEventRequests` REST resource.

Default path:

```text
/hcmRestApi/resources/11.13.18.05/timeEventRequests
```

The exact tenant base URL, authentication method, `sourceId`, supplier event codes and Oracle mappings must be validated with the Oracle implementation team before enabling production delivery.

## Payload

One local event is sent per request in the initial implementation:

```json
{
  "requestNumber": "BSS-J35-01H...",
  "sourceId": "HWM_CLOCK_TIME",
  "requestTimestamp": "2026-10-09T16:45:12.000+00:00",
  "timeEvents": [
    {
      "deviceId": "J35",
      "eventDateTime": "2026-10-09T18:45:10.321+02:00",
      "supplierDeviceEvent": "BSS_START_WORK",
      "reporterId": "84729",
      "reporterIdType": "BADGE"
    }
  ]
}
```

Optional action-level `timeEventAttributes` can be configured as JSON and are included only when present.

## Local-only fields

The following fields are retained locally and are not sent unless a later Oracle requirement explicitly asks for them:

- Internal UUID.
- Identification method (`RFID` or `KEYPAD`).
- Internal action code/label.
- Local delivery status.
- Retry counters.
- Technical logs.

## Delivery statuses

- `PENDING`: captured locally and waiting for delivery.
- `SENDING`: currently claimed by the worker.
- `RETRY`: a non-ambiguous transient failure occurred.
- `SENT`: Oracle accepted the HTTP request.
- `REJECTED`: Oracle returned a non-retryable response.
- `UNKNOWN`: delivery outcome is ambiguous, typically after a read/write timeout. Manual reconciliation is required before replay.

A successful HTTP response is a delivery acknowledgement. Oracle remains responsible for downstream functional validation and business processing.
