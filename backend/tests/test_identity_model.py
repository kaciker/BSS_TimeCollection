from datetime import datetime, timezone
from hashlib import sha256

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.domain.enums import IdentificationMethod, WorkerState
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.models.perimeter import FactoryPerimeterSettings, TerminalBadgeRead
from app.models.time_event import TimeEvent
from app.models.terminal import Terminal
from app.models.transmission_attempt import TransmissionAttempt
from app.services import event_service
from app.services.person_identity import (
    PersonIdentity,
    PersonIdentityError,
    resolve_person_identity,
    resolve_person_identity_by_employee_id,
)
from app.services.state_service import derive_worker_state
from test_configuration import activate_created_terminal, configured_terminal
from test_monitoring import monitor


def identity(person="3627", reader=None):
    return PersonIdentity(
        source_person_id=f"PERSON-PK-{person}",
        person_id=person,
        source_card_id="CARD-PK" if reader else None,
        credential_id="CREDENTIAL" if reader else None,
        reader_id=reader,
    )


def test_keypad_resolves_pin_without_card_join_and_keeps_text_semantics():
    calls = []
    resolved = resolve_person_identity_by_employee_id(" 003627 ", query=lambda pin: calls.append(pin) or [("SOURCE-1", pin)])
    assert calls == ["003627"]
    assert resolved.person_id == "003627"
    assert resolved.source_person_id == "SOURCE-1"
    assert resolved.credential_id is None
    assert resolved.reader_id is None


def test_keypad_person_lookup_rejects_unknown_ambiguous_and_query_failure():
    with pytest.raises(PersonIdentityError, match="PERSON_NOT_FOUND"):
        resolve_person_identity_by_employee_id("unknown", query=lambda _pin: [])
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_PERSON"):
        resolve_person_identity_by_employee_id("3627", query=lambda pin: [("P1", pin), ("P2", pin)])
    with pytest.raises(PersonIdentityError, match="QUERY_FAILED"):
        resolve_person_identity_by_employee_id("3627", query=lambda _pin: 1 / 0)


def test_existing_rfid_resolver_keeps_raw_reader_and_byte_swap_behavior():
    seen = []
    result = resolve_person_identity(
        "0537312724",
        query=lambda raw, swapped: seen.append((raw, swapped)) or [
            (raw, "SOURCE-1", "3627", "CARD-1", "CARD-A", "3627")
        ],
    )
    assert seen == [("0537312724", "3569157664")]
    assert result.person_id == "3627"
    assert result.reader_id == "0537312724"


def test_same_employee_resolves_to_same_canonical_person_across_methods():
    keypad = resolve_person_identity_by_employee_id("3627", query=lambda pin: [("PK-3627", pin)])
    rfid = resolve_person_identity(
        "0537312724",
        query=lambda raw, swapped: [(raw, "PK-3627", "3627", "CARD-PK", "0537312724", "3627")],
    )
    assert keypad.person_id == rfid.person_id == "3627"
    assert keypad.reader_id is None
    assert rfid.reader_id == "0537312724"


def test_rfid_not_found_category_is_preserved():
    with pytest.raises(PersonIdentityError, match="IDENTITY_NOT_FOUND"):
        resolve_person_identity("0537312724", query=lambda _raw, _swapped: [])


@pytest.mark.parametrize(
    ("entry_method", "entry_reporter", "exit_method", "exit_reporter"),
    [
        (IdentificationMethod.KEYPAD, "3627", IdentificationMethod.RFID, "0537312724"),
        (IdentificationMethod.RFID, "0537312724", IdentificationMethod.KEYPAD, "3627"),
    ],
)
def test_cross_method_worker_timeline_and_reporter_preservation(
    monitor, monkeypatch, entry_method, entry_reporter, exit_method, exit_reporter
):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    activate_created_terminal(client, terminal)
    db.add(FactoryPerimeterSettings(factory_code="ARGANDA", enabled=False, badge_source="EXTERNAL", dedup_enabled=False, dedup_seconds=5))
    db.commit()
    person_by_method = {
        IdentificationMethod.KEYPAD: identity("3627"),
        IdentificationMethod.RFID: identity("3627", "0537312724"),
    }
    monkeypatch.setattr(
        event_service,
        "_resolve_capture_identity",
        lambda _db, _config, _reporter, method, _now: person_by_method[method],
    )

    entered = event_service.scan(db, "CLOCK-A", entry_reporter, entry_method)
    assert entered.flow == "ENTRY_RECORDED"
    entry_event = db.get(TimeEvent, entered.event.id)
    assert entry_event.reporter_id == entry_reporter
    assert entry_event.person_id == "3627"
    assert entry_event.source_person_id == "PERSON-PK-3627"
    assert entry_event.credential_id == ("CREDENTIAL" if entry_method == IdentificationMethod.RFID else None)
    assert entry_event.oracle_reporter_id == "3627"
    assert entry_event.oracle_reporter_id_type == "PERSON"
    assert derive_worker_state(db, exit_reporter, "ARGANDA", person_id="3627") == WorkerState.INSIDE

    pending = event_service.scan(db, "CLOCK-A", exit_reporter, exit_method)
    assert pending.flow == "EXIT_REQUIRED"
    exited = event_service.record_exit(db, "CLOCK-A", exit_reporter, exit_method, "STOP")
    assert exited.flow == "EXIT_RECORDED"
    exit_event = db.get(TimeEvent, exited.event.id)
    assert exit_event.reporter_id == exit_reporter
    assert exit_event.person_id == "3627"
    assert exit_event.oracle_reporter_id == "3627"
    assert exit_event.oracle_reporter_id_type == "PERSON"
    assert derive_worker_state(db, entry_reporter, "ARGANDA", person_id="3627") == WorkerState.OUTSIDE
    cards = client.get("/api/v1/admin/monitoring/cards?reporter_id=3627").json()
    assert cards["total"] == 1
    assert cards["items"][0]["person_id"] == "3627"
    assert cards["items"][0]["reporter_id"] == exit_reporter
    assert db.scalar(select(func.count()).select_from(PersonBadgeAssignment).where(PersonBadgeAssignment.reader_id == "3627")) == 0
    assert db.scalar(select(func.count()).select_from(PersonBadgeAssignment).where(PersonBadgeAssignment.reader_id == "0537312724")) == 1
    assert db.scalar(select(func.count()).select_from(TransmissionAttempt)) == 0


def test_keypad_unknown_fails_before_any_new_event(monitor, monkeypatch):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    activate_created_terminal(client, terminal)
    db.add(FactoryPerimeterSettings(factory_code="ARGANDA", enabled=False, badge_source="EXTERNAL", dedup_enabled=False, dedup_seconds=5))
    db.commit()
    monkeypatch.setattr(event_service, "_resolve_capture_identity", lambda *_: (_ for _ in ()).throw(HTTPException(404, "PERSON_NOT_FOUND")))
    response = client.post(
        "/api/v1/terminal/scan",
        json={"reporter_id": "missing", "identification_method": "KEYPAD"},
    )
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 0


def test_duplicate_window_uses_person_across_reporters(monitor, monkeypatch):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    activate_created_terminal(client, terminal)
    db.add(FactoryPerimeterSettings(factory_code="ARGANDA", enabled=False, badge_source="EXTERNAL", dedup_enabled=True, dedup_seconds=5))
    db.commit()
    person_by_method = {
        IdentificationMethod.KEYPAD: identity("3627"),
        IdentificationMethod.RFID: identity("3627", "0537312724"),
    }
    monkeypatch.setattr(event_service, "_resolve_capture_identity", lambda _db, _config, _reporter, method, _now: person_by_method[method])
    first = event_service.scan(db, "CLOCK-A", "3627", IdentificationMethod.KEYPAD)
    second = event_service.scan(db, "CLOCK-A", "0537312724", IdentificationMethod.RFID)
    assert first.flow == "ENTRY_RECORDED"
    assert second.flow == "EXIT_REQUIRED"
    reads = db.scalars(select(TerminalBadgeRead)).all()
    assert len(reads) == 1
    assert reads[0].reporter_id == "person:3627"
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 1


def test_rfid_observation_keeps_multiple_physical_credentials_for_same_person(monitor):
    from app.services.person_identity import observe_identity

    _client, db = monitor
    first = PersonIdentity("PK-3627", "3627", "CARD-1", "CRED-1", "0537312724")
    second = PersonIdentity("PK-3627", "3627", "CARD-2", "CRED-2", "1111111111")
    observe_identity(db, "ARGANDA", first)
    observe_identity(db, "ARGANDA", second)
    db.flush()
    assignments = db.scalars(select(PersonBadgeAssignment).order_by(PersonBadgeAssignment.id)).all()
    assert len(assignments) == 2
    assert {row.reader_id for row in assignments} == {"0537312724", "1111111111"}
    assert all(row.person_id == "3627" for row in assignments)


def test_canonical_lock_hash_is_shared_across_methods():
    class PostgreSQL:
        name = "postgresql"

    class Bind:
        dialect = PostgreSQL()

    class FakeDB:
        calls = []
        def get_bind(self):
            return Bind()
        def execute(self, statement, params):
            self.calls.append(params["key"])

    db = FakeDB()
    event_service._lock_badge(db, "3627", "3627")
    event_service._lock_badge(db, "0537312724", "3627")
    expected = int.from_bytes(sha256(b"person:3627").digest()[:8], "big", signed=True)
    assert db.calls == [expected, expected]


def test_legacy_null_person_event_keeps_reporter_fallback(monitor):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    event = TimeEvent(
        id="legacy-null-person", request_number="BSS-legacy-null-person",
        terminal_id=db.scalar(select(Terminal).where(Terminal.code == "CLOCK-A")).id,
        action_id=1, terminal_code="CLOCK-A", device_id="CLOCK-A", action_code="START",
        action_label="Start", supplier_device_event="BSS_START", state_effect="ENTER",
        reporter_id="OLD-READER", reporter_id_type="BADGE", identification_method="RFID",
        event_datetime=datetime.now(timezone.utc), event_timezone="Europe/Madrid", oracle_attributes={},
        person_id=None, delivery_status="PENDING",
    )
    db.add(event)
    db.commit()
    assert derive_worker_state(db, "OLD-READER", "ARGANDA") == WorkerState.INSIDE
    assert derive_worker_state(db, "OTHER-READER", "ARGANDA", person_id="3627") == WorkerState.OUTSIDE


@pytest.mark.parametrize(
    ("terminal_mode", "method", "expected_status"),
    [
        ("BOTH", "KEYPAD", 200),
        ("BOTH", "RFID", 200),
        ("KEYPAD", "KEYPAD", 200),
        ("KEYPAD", "RFID", 409),
        ("RFID", "RFID", 200),
        ("RFID", "KEYPAD", 409),
    ],
)
def test_terminal_identification_mode_accepts_only_configured_methods(
    monitor, terminal_mode, method, expected_status
):
    client, _db = monitor
    terminal, payload = configured_terminal(client)
    payload["identification_mode"] = terminal_mode
    updated = client.put(f"/api/v1/admin/terminals/{terminal['code']}", json=payload)
    assert updated.status_code == 200, updated.text
    activation = client.post("/api/v1/terminal/activate", json={"token": terminal["activation_token"]})
    assert activation.status_code == 200, activation.text
    response = client.post(
        "/api/v1/terminal/scan",
        json={"reporter_id": "3627" if method == "KEYPAD" else "0537312724", "identification_method": method},
    )
    assert response.status_code == expected_status


def test_exit_policy_accepts_cross_method_reporter_for_same_person(monitor):
    _client, db = monitor
    terminal, _ = configured_terminal(_client)
    activate_created_terminal(_client, terminal)
    db.add(FactoryPerimeterSettings(factory_code="ARGANDA", enabled=False, badge_source="OPEN", dedup_enabled=False, dedup_seconds=0))
    db.commit()
    event_service._create_event(
        db,
        db.scalar(select(Terminal).where(Terminal.code == terminal["code"])),
        db.scalar(select(__import__("app.models.action", fromlist=["Action"]).Action).where(__import__("app.models.action", fromlist=["Action"]).Action.code == "START")),
        "3627",
        IdentificationMethod.KEYPAD,
        identity=identity("3627"),
    )
    from app.services.exit_policy import check_exit_policy, save_mode
    save_mode(db, db.scalar(select(Terminal).where(Terminal.code == terminal["code"])).id, "SAME_TERMINAL")
    check_exit_policy(
        db,
        db.scalar(select(Terminal).where(Terminal.code == terminal["code"])),
        "0537312724",
        person_id="3627",
    )
