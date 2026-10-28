# Person ID and badge identity model

## Decision

BSS Time Collection separates the stable person identity from the replaceable physical credential.

For factories using the read-only `SQLSERVER_SECURITY_DB` perimeter source:

- `pers_person.id` is retained as the source-system technical person key.
- `pers_person.pin` is retained as the functional Person ID.
- `pers_card.card_no` is retained as the current physical credential/card identifier.
- The RFID value received from the terminal remains in `time_events.reporter_id` for backwards compatibility and technical correlation.
- New events freeze the resolved person/card relationship at capture time.
- Oracle delivery uses the frozen `oracle_reporter_id` and `oracle_reporter_id_type`, not a later lookup.

No names, addresses, email addresses, national IDs or other employee profile fields are imported.

## Read-only source contract

BSS never writes to `SECURITY_DB`.

Current identity resolution is:

```text
reader RFID
  -> pers_attribute_ext.attr_value4
  -> pers_person.id / pers_person.pin
  -> pers_card.id / pers_card.card_no
```

The adapter rejects unresolved, inconsistent or ambiguous current mappings rather than guessing.

`pers_issuecard` is not imported as authoritative assignment history. The 28 October 2026 database audit showed that it lacks immutable `person_id`, contains reused cards and PINs, and does not cover every current pair reliably.

## Local traceability

`person_badge_assignments` stores observed current assignments:

- factory
- source person key
- Person ID
- source card row key
- credential/card number
- first/last observation
- observed interval

The worker periodically reads the complete current `pers_card -> pers_person` snapshot and closes/opens local observed intervals when the relationship changes. `observed_from` and `observed_to` are BSS observation times; they are not claimed to be the exact SECURITY_DB administrative change time.

This provides reliable forward traceability from deployment without inventing an unreliable historical reconstruction.

## Event snapshot

New `time_events` fields are nullable so historical rows remain valid:

```text
source_person_id
person_id
credential_id
oracle_reporter_id
oracle_reporter_id_type
```

Existing `reporter_id` is intentionally preserved as the raw terminal identifier.

Worker state and exit-policy evaluation prefer `person_id` when available and fall back to the legacy raw identifier for old/unmapped events. This means replacing a card does not create a new worker identity.

Factory-exit cascade also resolves the current Person ID so an exit made with a replacement card can close the person's active cell event.

## Oracle

For a resolved SECURITY_DB identity the event snapshot uses:

```text
oracle_reporter_id      = pers_person.pin
oracle_reporter_id_type = ORACLE_PERSON_REPORTER_ID_TYPE
```

The default type is `PERSON`, but it is deployment-configurable because the Oracle implementation team must confirm whether this tenant expects `PERSON` or `PERSONID` for the value stored in `pers_person.pin`.

Legacy/unmapped events continue to fall back to `ORACLE_REPORTER_ID_TYPE` and the original `reporter_id`.

## Deployment notes

Apply Alembic revision:

```text
0015_person_badge_identity
```

Set or confirm:

```text
ORACLE_PERSON_REPORTER_ID_TYPE=PERSON
PERSON_BADGE_SYNC_SECONDS=180
```

Before enabling Oracle delivery, validate one known employee end-to-end:

1. RFID resolves to one current SECURITY_DB person/card row.
2. `person_id` equals the intended Oracle reporter value.
3. Replacing the card closes the old local observed assignment and opens the new one.
4. New time events keep the old/new credential that was effective at capture time.
5. Oracle preview uses Person ID while the event retains the physical credential snapshot.
