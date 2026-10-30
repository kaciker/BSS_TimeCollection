# Oracle Time Event Contract

The Oracle adapter targets the Oracle HCM Time and Labor `timeEventRequests` REST resource.

Default path:

```text
/hcmRestApi/resources/11.13.18.05/timeEventRequests
```

## CORP proof of concept target

- Environment: Oracle DEV2 (`https://fa-eocc-dev2-saasfaprod1.fa.ocs.oraclecloud.com`)
- Resource: `/hcmRestApi/resources/11.13.18.05/timeEventRequests`
- Authentication: the deployed client supports HTTP Basic and Bearer credentials. A streamed, authenticated `GET .../timeEventRequests/describe` against the configured DEV2 tenant returned HTTP 200 on 2026-10-30. It validates metadata read access only; it does not prove that the event-create privilege is granted.
- Required `REST-Framework-Version: 4` header (alongside JSON `Accept` and `Content-Type`).
- `sourceId`: `HUT_TCD_SUPP1`
- `reporterIdType`: `PERSON`; `reporterId` comes only from the resolved Person ID frozen on the captured event. Badge values remain local audit data and are never a fallback.
- `ORACLE_ENABLED=false` remains in CORP until real credentials are received and validated.

The BSS Workshop / Subworkshop / Project-Line structure is the authoritative operational structure for this POC. Do not import or replace it with the older HR-Path Excel workbook used for their initial test.

## Mappings

Each cell event freezes its complete structure codes at capture. Oracle attributes derive from this snapshot: `WORK_AREA = workshop_code`, `MACHINE = subworkshop_code`, and `CELL = project_line_code`. Incomplete paths and missing Person IDs are retained locally and flagged for reconciliation, without sending a request.

Supplier device events represent direction and may be shared among actions: ENTER uses `HUT_TCD_SUPP1_IN_2`, EXIT uses `HUT_TCD_SUPP1_OUT_2`. Migration removes only the action supplier-event uniqueness constraint; existing action values and historical snapshots are preserved.

`PayrollTimeType` is an explicit per-action mapping. Administrators must fill it only after the action mapping has been confirmed with HR-Path. Examples from HR-Path are `Workshop Entry ES`, `Project Entry ES`, `Non-productive time ES`, and `Break ES`; no BSS action is assigned a value automatically. Advanced action attributes remain available for exceptional attributes.

Administration distinguishes whether connection credentials are configured from whether delivery is enabled. The safe connectivity check only contacts the HTTPS base host; it does not send a time event or claim that authentication was accepted. Full authentication validation awaits credentials and a supported Oracle validation endpoint.

## Oracle metadata verification (2026-10-30)

The configured tenant's read-only `GET /hcmRestApi/resources/11.13.18.05/timeEventRequests/describe` returned HTTP 200. The `Resources.timeEventRequests` metadata declares a `create` action using HTTP `POST`, with JSON and Oracle ADF resource-item media types. The request resource fields `requestNumber`, `requestTimestamp`, and `sourceId` are mandatory and input-required; described maximum lengths are 80, 80, and 40 characters respectively. `timeEvents` is a child collection with cardinality 1 to many.

The child event metadata marks `eventDateTime`, `reporterId`, and `reporterIdType` as mandatory/input-required. `eventDateTime` must use ISO 8601 including a time-zone offset. `deviceId` (40 chars) and `supplierDeviceEvent` (40 chars) are optional in generic metadata, although this CORP mapping supplies them. `reporterId` permits 80 chars. The reporter type LOV describes `BADGE`, `PERSON`, `PERSONID`, and `ASSIGNMENT`; CORP currently maps a resolved frozen Person ID as `PERSON`.

The child `timeEventAttributes` collection requires `name` and `value`; the metadata describes maximum lengths of 240 and 150. It does not identify tenant-specific required attribute names or valid business codes. CORP mappings `WORK_AREA`, `MACHINE`, `CELL`, and action `PayrollTimeType` values therefore remain project/HR-Path mappings that need Oracle/HR-Path functional confirmation; they are not inferred from this generic resource schema.

This metadata response establishes the resource shape, create method, required fields, selected size limits, and event timestamp-offset requirement. It does not establish the full create-response body, field-level validation error format, Oracle duplicate-request behavior/idempotency for repeated `requestNumber`, tenant supplier-event lookup values, or event-creation privilege. No event POST, employee query, or write request was made. The generic metadata calls `requestNumber` a unique identifier; BSS additionally enforces local uniqueness and sends one event per request. A timeout after POST remains ambiguous and is not automatically replayed.

## Payload

One local event is sent per request in the initial implementation:

```json
{
  "requestNumber": "BSS-J35-01H...",
  "sourceId": "HUT_TCD_SUPP1",
  "requestTimestamp": "2026-10-09T16:45:12.000+00:00",
  "timeEvents": [
    {
      "deviceId": "J35",
      "eventDateTime": "2026-10-09T18:45:10.321+02:00",
      "supplierDeviceEvent": "HUT_TCD_SUPP1_IN_2",
      "reporterId": "104582",
      "reporterIdType": "PERSON",
      "timeEventAttributes": [
        {"name": "PayrollTimeType", "value": "Workshop Entry ES"},
        {"name": "WORK_AREA", "value": "439"},
        {"name": "MACHINE", "value": "4393"},
        {"name": "CELL", "value": "54A"}
      ]
    }
  ]
}
```

`eventDateTime` remains the captured event time. `requestTimestamp` remains the actual transmission time. HR-Path's example shows equal timestamps, but this behavior remains intentionally unchanged pending confirmation.

Oracle credentials must never be stored in Git. The example configuration contains blank credential variables only.

## Oracle field limits

The application validates Oracle-bound identifiers before configuration or capture so invalid events are not persisted for delivery:

| Field | Maximum length |
| --- | ---: |
| `deviceId` / terminal `external_device_id` | 40 characters |
| `supplierDeviceEvent` | 40 characters |
| `reporterId` | 80 characters |

Database snapshot columns retain their existing wider capacity for historical compatibility; the API boundary enforces the Oracle limits for new configuration and captures.

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
- `UNKNOWN`: delivery outcome is ambiguous. This includes read/write timeouts, stale `SENDING` records after worker recovery, and unhandled failures while an event is in `SENDING`. Manual reconciliation is required before replay.

A stale or interrupted `SENDING` event is never automatically replayed because Oracle may already have accepted it even when the local worker did not persist the acknowledgement.

A successful HTTP response is a delivery acknowledgement. The adapter extracts `timeEventRequestId` and child `timeEventId` when present, retaining request/response payloads in the local transmission attempt for audit. A successful HTTP response is not proof of downstream functional acceptance; Oracle remains responsible for downstream business processing.


## Verified against DEV2 Oracle metadata (2026-10-30)

An authenticated, read-only `GET .../timeEventRequests/describe` returned HTTP 200. The live resource metadata advertises `POST` on the collection with `application/vnd.oracle.adf.resourceitem+json` and `application/json`. It reports `requestNumber` (required, maximum 80 characters), `requestTimestamp` (required), and `sourceId` (required, maximum 40). Each `timeEvents` child requires `eventDateTime` (ISO 8601 with timezone offset), `reporterId` (maximum 80), and `reporterIdType` (maximum 30). `deviceId` (maximum 40) and `supplierDeviceEvent` (maximum 40) are optional in generic metadata; the CORP mapping populates both. Event attribute `name`/`value` limits are 240/150 characters. `timeEventRequestId` and `timeEventId` are generated identifiers.

The public Oracle Time Event Requests endpoint reference independently lists POST at the versioned collection path and GET collection/item operations. Tenant metadata is authoritative for the tenant-specific resource shape and lookup values. No event POST was made for this validation.

Metadata does not specify the business validation error body, duplicate semantics, uniqueness enforcement for `requestNumber`, or an idempotency token. Therefore HTTP 408/5xx and protocol failures after POST are ambiguous and are recorded as `UNKNOWN`, requiring reconciliation before replay. HTTP 425/429 and failures known to occur before connection establishment can be retried. Other nonretryable HTTP responses are `REJECTED`.

`eventDateTime` is the frozen capture time serialized in its original local timezone with offset. `requestTimestamp` is set at transmission time. HR-Path sample shows equal timestamps, but whether equality is mandatory remains unconfirmed. Oracle lists `BADGE`, `PERSON`, `PERSONID`, and `ASSIGNMENT` as reporter types; this POC sends only the resolved Person ID frozen on capture with type `PERSON`.

The accepted supplier event codes and `PayrollTimeType` for each action remain tenant/business mappings requiring HR-Path confirmation. The response acknowledgement and validation-error body schemas also need confirmation; current audit stores request/response bodies and extracts response IDs when present.
