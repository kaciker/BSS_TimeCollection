# Oracle authentication consolidation and contract verification — 2026-10-30

## Source and GitHub

The active CORP candidate is the recovered HR-Path source at `5e3a4d9`, with authentication work on `feature/corp-oracle-auth-settings-20261030` and subsequent external-source identity/idempotency changes. The same-named GitHub branch is a placeholder and is not its source. GitHub’s published `feature/person-badge-identity-traceability-20261028` is the closest published base. Consolidation is proposed as a new forward branch/PR from that base; it does not force-push or merge unrelated history. Runtime secrets and `.env` are excluded.

## Functional contract evidence

On 2026-10-30, the configured DEV2 credentials successfully performed GET-only against `/hcmRestApi/resources/11.13.18.05/timeEventRequests/describe` (HTTP 200). No Oracle event POST was made. The Oracle public Time Event Requests reference documents POST on the versioned `timeEventRequests` collection and GET collection/item routes. The live tenant metadata advertises JSON and Oracle ADF JSON media types for POST.

Live metadata requires request `requestNumber` (maximum 80), `requestTimestamp`, and `sourceId` (maximum 40). It requires event `eventDateTime` (ISO-8601 with offset, maximum 150), `reporterId` (maximum 80), and `reporterIdType` (maximum 30). Device ID and supplier-device event are optional in generic schema, maximum 40 each, but supplied by explicit CORP mapping. Event-attribute `name` and `value` maxima are 240 and 150. Oracle generates request/event IDs. Details and verified/unknown distinctions are in `docs/oracle-contract.md`.

CORP sends one event/request, using source `HUT_TCD_SUPP1`, frozen resolved Person ID with type `PERSON`, captured timestamp in its local zone/offset, and explicit per-action PayrollTimeType. The operational Workshop/Subworkshop/Project-Line snapshots map only to configured `WORK_AREA`/`MACHINE`/`CELL`. No badge fallback or inferred mapping is allowed.

No duplicate/idempotency guarantee or error response body schema was found in live metadata or the public endpoint reference. Therefore ambiguous HTTP 408/5xx and post-send protocol outcomes become `UNKNOWN` and require manual reconciliation; only pre-connect failures and HTTP 425/429 retry. Local request numbers remain uniquely constrained; overlength generated request numbers preserve the full UUID and bound the terminal prefix.

## Validation

- Backend suite on active candidate source: 197 passed, 7 skipped.
- Frontend: 66 passed; Node 22/Vite production build succeeded.
- Payload, identity, direction, offset/time-zone, field limits, event ordering, retry classification, duplicate protection, attempt audit and disabled-worker behavior use synthetic events/mocks.
- Live stack before this consolidation: API/web/database healthy; Oracle delivery false. Database had 0 transmission attempts. Worker/database/volume IDs and `.env` preserved.

## Safe deployment and rollback

Before deploying any candidate, make and verify a timestamped database/config/source backup, including container image IDs and mounts; keep credential and SQL credential files outside source control. Keep `ORACLE_ENABLED=false`. Build candidate API/web images without starting a worker. Recreate only changed application services; do not run `down`, `down -v`, or recreate PostgreSQL. Inspect migration current/head and preserve the existing PGDATA anonymous mount and named volume. Validate health/readiness, runtime Oracle flag, and unchanged attempt count. Do not invoke `timeEventRequests` POST or enable scheduling.

Rollback by recreating only changed application service(s) with image IDs/tags recorded in the predeployment backup. Do not restore or replace PostgreSQL volumes for an application-only rollback. If a migration has been applied, stop before destructive downgrade and use the verified DB backup/recovery procedure with the database owner.

## Controlled end-to-end acceptance requirements

Before any event POST: HR-Path must approve the authenticated endpoint/environment; provide confirmed create permission; confirm accepted `sourceId`, supplier event lookup codes/directions, per-action PayrollTimeType, all operational attributes and Person-ID source; confirm requestTimestamp/eventDateTime equality expectations, request/response and validation-error schemas, duplicate handling/idempotency and retry rules. Reconcile all `UNKNOWN` and `REJECTED` records. Then use an approved non-production tenant and an authorized synthetic/test person with an explicit test window and event, independent Oracle-side monitoring, one event at a time, and a stop/rollback contact. Start with Oracle disabled, enable delivery only for that approved window, verify exactly one Oracle event and its identifiers/audit, then disable delivery and confirm no further attempts. No real employee attendance records are in scope.
