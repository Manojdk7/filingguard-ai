import os
import sqlite3
import tempfile
import pytest

from app.audit.hashing import GENESIS_PREVIOUS_HASH
from app.audit.ledger import AuditLedgerService
from app.database.models import CREATE_AUDIT_EVENTS_TABLE_SQL
from app.database.repositories.audit_repository import AuditRepository


@pytest.fixture
def temp_audit_repo():
    """Create an isolated, temporary SQLite database for audit ledger testing."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_audit.db")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(CREATE_AUDIT_EVENTS_TABLE_SQL)

    # Monkeypatch get_db_connection to use test DB
    from contextlib import contextmanager

    @contextmanager
    def mock_get_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.database.repositories.audit_repository.get_db_connection", mock_get_conn)
        repo = AuditRepository()
        yield repo, db_path

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_genesis_event_creation(temp_audit_repo):
    """Test 1: First audit event links to GENESIS_PREVIOUS_HASH and receives sequence #1."""
    repo, _ = temp_audit_repo
    service = AuditLedgerService(audit_repo=repo)

    evt = service.record_event(
        event_type="WORKFLOW_STARTED",
        actor="system",
        payload={"workflow_id": "wf_test_001", "accession": "test-accn"},
        accession_number="test-accn",
    )

    assert evt.sequence_num == 1
    assert evt.previous_hash == GENESIS_PREVIOUS_HASH
    assert len(evt.event_hash) == 64
    assert evt.event_type == "WORKFLOW_STARTED"
    assert evt.actor == "system"


def test_linear_hash_chaining(temp_audit_repo):
    """Test 2: Sequential events correctly link each event's previous_hash to the prior event_hash."""
    repo, _ = temp_audit_repo
    service = AuditLedgerService(audit_repo=repo)

    evt1 = service.record_event(
        event_type="FACTS_EXTRACTED",
        actor="system",
        payload={"facts_count": 10},
    )
    evt2 = service.record_event(
        event_type="VALIDATION_COMPLETED",
        actor="system",
        payload={"rules_passed": 14},
    )
    evt3 = service.record_event(
        event_type="REVIEW_DECISION_RECORDED",
        actor="auditor_jane",
        payload={"decision": "APPROVED", "metric": "revenue"},
    )

    assert evt1.sequence_num == 1
    assert evt1.previous_hash == GENESIS_PREVIOUS_HASH

    assert evt2.sequence_num == 2
    assert evt2.previous_hash == evt1.event_hash

    assert evt3.sequence_num == 3
    assert evt3.previous_hash == evt2.event_hash

    # All events are stored in order
    all_events = service.get_events()
    assert len(all_events) == 3
    assert [e.sequence_num for e in all_events] == [1, 2, 3]


def test_duplicate_event_suppression(temp_audit_repo):
    """Test 3: Exact duplicate event submission is idempotently returned without creating duplicate entries."""
    repo, _ = temp_audit_repo
    service = AuditLedgerService(audit_repo=repo)

    evt1 = service.record_event(
        event_type="REVIEW_DECISION_RECORDED",
        actor="lead_auditor",
        payload={"decision": "APPROVED", "metric_id": "revenue"},
        accession_number="test-accn",
        metric_id="revenue",
    )

    evt2 = service.record_event(
        event_type="REVIEW_DECISION_RECORDED",
        actor="lead_auditor",
        payload={"decision": "APPROVED", "metric_id": "revenue"},
        accession_number="test-accn",
        metric_id="revenue",
    )

    assert evt1.event_id == evt2.event_id
    assert evt1.sequence_num == evt2.sequence_num
    assert repo.count_events() == 1


def test_missing_actor_or_type_raises_value_error(temp_audit_repo):
    """Test 4: Omitting actor or event_type is rejected."""
    repo, _ = temp_audit_repo
    service = AuditLedgerService(audit_repo=repo)

    with pytest.raises(ValueError, match="Actor identity is mandatory"):
        service.record_event(event_type="TEST", actor="   ", payload={})

    with pytest.raises(ValueError, match="Event type is mandatory"):
        service.record_event(event_type="", actor="auditor", payload={})

