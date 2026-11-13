import pytest

from app.audit.hashing import GENESIS_PREVIOUS_HASH, calculate_event_hash
from app.audit.verification import AuditVerifier
from app.database.repositories.audit_repository import AuditEventRecord


def _build_mock_event(seq: int, prev_hash: str, payload: dict, event_type: str = "TEST") -> AuditEventRecord:
    timestamp = f"2026-01-0{seq}T00:00:00Z"
    h = calculate_event_hash(prev_hash, payload, timestamp)
    return AuditEventRecord(
        event_id=f"evt_mock_{seq}",
        sequence_num=seq,
        event_type=event_type,
        actor="auditor_jane",
        payload=payload,
        previous_hash=prev_hash,
        event_hash=h,
        created_at=timestamp,
    )


def test_valid_chain_verification():
    """Test 1: An untampered hash chain verifies cleanly as VALID."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"action": "retrieve"})
    evt2 = _build_mock_event(2, evt1.event_hash, {"action": "extract"})
    evt3 = _build_mock_event(3, evt2.event_hash, {"action": "validate"})

    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[evt1, evt2, evt3])

    assert res.is_valid is True
    assert res.status == "VALID"
    assert res.total_events == 3
    assert res.first_tampered_event_id is None
    assert res.failure_reason is None
    assert res.latest_event_hash == evt3.event_hash


def test_empty_chain_is_valid():
    """Test 2: Empty ledger verifies as VALID with 0 events."""
    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[])

    assert res.is_valid is True
    assert res.status == "VALID"
    assert res.total_events == 0


def test_tampered_payload_detected():
    """Test 3: Altering a single field in an event's payload returns TAMPERED and identifies the event."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"action": "retrieve", "docs": 1})
    evt2 = _build_mock_event(2, evt1.event_hash, {"action": "review", "decision": "APPROVED", "value": 1000000.0})
    evt3 = _build_mock_event(3, evt2.event_hash, {"action": "complete"})

    # Tamper with event 2's payload: modify value from 1000000.0 to 999999.0
    tampered_evt2 = evt2.model_copy(update={"payload": {"action": "review", "decision": "APPROVED", "value": 999999.0}})

    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[evt1, tampered_evt2, evt3])

    assert res.is_valid is False
    assert res.status == "TAMPERED"
    assert res.first_tampered_sequence == 2
    assert res.first_tampered_event_id == evt2.event_id
    assert "Cryptographic hash mismatch" in res.failure_reason
    assert "payload or timestamp was altered" in res.failure_reason


def test_tampered_event_hash_detected():
    """Test 4: Forging or altering the event_hash returns TAMPERED."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"step": 1})
    # Alter the hash directly
    tampered_evt1 = evt1.model_copy(update={"event_hash": "f" * 64})

    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[tampered_evt1])

    assert res.is_valid is False
    assert res.status == "TAMPERED"
    assert res.first_tampered_sequence == 1
    assert "hash mismatch" in res.failure_reason.lower()


def test_broken_previous_hash_pointer_detected():
    """Test 5: Broken previous_hash pointer between consecutive events returns TAMPERED."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"step": 1})
    evt2 = _build_mock_event(2, evt1.event_hash, {"step": 2})

    # Point event 2's previous_hash to an invalid hash
    tampered_evt2 = evt2.model_copy(update={"previous_hash": "e" * 64})

    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[evt1, tampered_evt2])

    assert res.is_valid is False
    assert res.status == "TAMPERED"
    assert res.first_tampered_sequence == 2
    assert "Broken previous-hash reference" in res.failure_reason


def test_missing_or_deleted_event_detected():
    """Test 6: Deleting an event causes broken sequence and is flagged as TAMPERED."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"step": 1})
    evt2 = _build_mock_event(2, evt1.event_hash, {"step": 2})
    evt3 = _build_mock_event(3, evt2.event_hash, {"step": 3})

    # Delete event 2 from the sequence: [evt1, evt3]
    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[evt1, evt3])

    assert res.is_valid is False
    assert res.status == "TAMPERED"
    assert res.first_tampered_sequence == 3
    assert "Broken sequence ordering" in res.failure_reason


def test_reordered_events_detected():
    """Test 7: Reordering events returns TAMPERED."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"step": 1})
    evt2 = _build_mock_event(2, evt1.event_hash, {"step": 2})

    # Swap event order: [evt2, evt1]
    verifier = AuditVerifier()
    res = verifier.verify_chain(events=[evt2, evt1])

    assert res.is_valid is False
    assert res.status == "TAMPERED"


def test_checkpoint_export():
    """Test 8: Checkpoint export contains valid signature and status."""
    evt1 = _build_mock_event(1, GENESIS_PREVIOUS_HASH, {"step": 1})
    verifier = AuditVerifier()
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(verifier.audit_repo, "get_all_events", lambda **kw: [evt1])
        cp = verifier.export_checkpoint()

        assert cp["status"] == "VALID"
        assert cp["is_valid"] is True
        assert cp["total_events"] == 1
        assert cp["latest_event_hash"] == evt1.event_hash
        assert len(cp["signature"]) == 64

