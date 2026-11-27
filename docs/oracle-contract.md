# Oracle Time Event Contract

## Verified DEV2 create test - 31 October 2026

The 31 October controlled create below records the earlier `PERSON` contract. On 26 November 2026 Hutchinson confirmed that the existing employee code sent in `reporterId` is exactly the Badge ID mapped and loaded into DEV2 by HR Path. The final contract keeps that value unchanged and sets `reporterIdType=BADGE`. No compatibility path is supported.

A controlled real create test succeeded in CORP against Oracle tenant DEV2. The POST was made once and was not retried. Authenticated GETs then reconciled the request number and generated request/event IDs. This verifies create permission and the exact controlled values below; the sample Person ID and structure values are not global defaults.

| Contract item | Verified value |
| --- | --- |
| Environment / tenant | CORP / DEV2 |
| Endpoint | `https://fa-eocc-dev2-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/11.13.18.05/timeEventRequests` |
| Request number | `BSS-POC-20261031T112527Z-a9effbeeb3e24d8aa48299735bf314e9` |
| `sourceId` | `HUT_TCD_SUPP1` |
| `reporterIdType` | `PERSON` (historical test; superseded by final `BADGE` contract) |
| Controlled test Person ID | `23703` |
| `supplierDeviceEvent` | `HUT_TCD_SUPP1_IN_2` accepted |
| `PayrollTimeType` | `Workshop Entry ES` accepted |
| `WORK_AREA` | `439` |
| `MACHINE` | `4393` |
| `CELL` | `54A` |
| Matching request/event timestamp | `2026-10-31T11:25:27.600Z` accepted |
| Oracle request ID / event ID | `300001304070001` / `300001304070002` |
| Reconciliation | GET returned HTTP 200 and matching request number and IDs |

Sanitized successful request:

```json
{
  "requestNumber": "BSS-POC-20261031T112527Z-a9effbeeb3e24d8aa48299735bf314e9",
  "sourceId": "HUT_TCD_SUPP1",
  "requestTimestamp": "2026-10-31T11:25:27.600Z",
  "timeEvents": [{
    "eventDateTime": "2026-10-31T11:25:27.600Z",
    "supplierDeviceEvent": "HUT_TCD_SUPP1_IN_2",
    "reporterId": "23703",
    "reporterIdType": "PERSON",
    "timeEventAttributes": [
      {"name": "PayrollTimeType", "value": "Workshop Entry ES"},
      {"name": "WORK_AREA", "value": "439"},
      {"name": "MACHINE", "value": "4393"},
      {"name": "CELL", "value": "54A"}
    ]
  }]
}
```

`deviceId` was not sent; Oracle GET returned `deviceId: null`.

### Read-only reconciliation findings

Authenticated GETs returned HTTP 200 for the request resource, `timeEvents` child, event item, and `timeEventAttributes` child. Request fields: `timeEventRequestId=300001304070001`, the request number above, `requestTimestamp=2026-10-31T11:25:27.600Z`, `sourceId=HUT_TCD_SUPP1`. Request links: `self`, `canonical`, child collection `timeEvents`.

Event fields from the historical 31 October response: `timeEventId=300001304070002`, `timeEventRequestId=300001304070001`, `eventDateTime=2026-10-31T11:25:27.600Z`, `deviceId=null`, `supplierDeviceEvent=HUT_TCD_SUPP1_IN_2`, `reporterId=23703`, `reporterIdType=PERSON`. That earlier test is evidence of the prior contract only; its historical response is not changed. The final contract is `reporterId=23703`, `reporterIdType=BADGE`.

The attributes child returned four rows, each with `facet=null`: `PayrollTimeType=Workshop Entry ES` (`timeEventAttributeId=300001304070003`), `WORK_AREA=439` (`...004`), `MACHINE=4393` (`...005`), `CELL=54A` (`...006`). Each row links to `self`, `canonical`, and parent event resources.

No returned field indicated processing status, validation status, processing result, error/rejection reason, downstream Time and Labor state, or created/updated timestamps. No provided link identified a processing-outcome resource. The actual observed value is **NOT_EXPOSED**; HTTP 200 and resource reconciliation do not establish downstream functional processing.

## Verified transport and authentication

Read-only metadata uses:

```http
GET /hcmRestApi/resources/11.13.18.05/timeEventRequests/describe
REST-Framework-Version: 4
Accept: application/json
```

Configured DEV2 Basic credentials returned HTTP 200 for metadata validation. Basic and Bearer credential modes are supported. JSON requests use `Accept: application/json`, `Content-Type: application/json`, and `REST-Framework-Version: 4`. Credentials stay outside source and logs.

## Current serializer contract

The final payload correction keeps the existing employee code (for example, `reporterId: 1838`) unchanged and changes only `reporterIdType` from `PERSON` to `BADGE`. Historical 31 October payload/GET evidence above remains intact. New snapshots, previews, and transmissions use the final contract below.

One local BSS event is sent per request:

- `requestNumber`: stable, locally unique BSS value, maximum 80 characters; unchanged between attempts.
- `sourceId`: configured `HUT_TCD_SUPP1`.
- `requestTimestamp` and `timeEvents[0].eventDateTime`: one UTC ISO timestamp with millisecond precision derived from captured `event_datetime`, serialized once for both fields. Delivery delay does not change it.
- `deviceId`: omitted from Oracle serialization; retained locally.
- `reporterId`: frozen resolved employee code from `person_id`, confirmed by Hutchinson as the Badge ID loaded into DEV2; `reporterIdType=BADGE`. The serialized value is unchanged; raw RFID/card is never a fallback.
- ENTER maps to `HUT_TCD_SUPP1_IN_2`; EXIT maps to `HUT_TCD_SUPP1_OUT_2`. Missing or direction-mismatched mapping blocks delivery.
- Exactly four attributes, in order: `PayrollTimeType`, `WORK_AREA`, `MACHINE`, `CELL`, from the frozen action mapping and workshop/subworkshop/project-line snapshots. Generic/local `oracle_attributes` remain local.
- All four values, Person ID, structure fields, and safe request number are required. Missing mappings retain the event locally for existing reconciliation/rejection handling; no defaults are invented.

The Person ID and mapping values in the validation table are for that controlled DEV2 test and are not production defaults.

## Remaining Oracle decisions

1. Full production supplier-event and workshop/subworkshop/project-line code catalogue.
2. Approved `PayrollTimeType` mapping for every action.
3. Live EXIT acceptance, not yet tested.
4. Oracle duplicate/idempotency behavior and request-number uniqueness scope.
5. Downstream functional processing semantics and how to establish application in Time and Labor.

Do not generalize the controlled test values or infer unresolved decisions from generic metadata.

## Duplicate safety, retry and audit

One local request number is preserved across attempts; no Oracle idempotency guarantee is assumed. HTTP 2xx becomes `SENT`; 400-class functional response becomes `REJECTED`; 425/429 and pre-connect failure follow retry policy. HTTP 408, 5xx, read/write timeouts, other post-send ambiguous protocol failures, and recovered stale `SENDING` events become `UNKNOWN` and are never blindly replayed.

Each attempt records endpoint, HTTP status, duration, sanitized request payload, response or bounded raw body, classification, applicable error, and returned Oracle IDs. Secrets are excluded. `ORACLE_ENABLED=false` prevents worker claims and transmissions.

## Local-only fields and limits

Internal UUID, RFID/KEYPAD method, local action code/label, raw badge/card identifier, terminal/device identity, delivery status, retry counters, technical logs, and generic/local `oracle_attributes` stay in BSS. Oracle metadata limits include request number 80, source ID 40, reporter ID 80, attribute name 240, and attribute value 150 characters. Historical snapshots retain their database capacity.
