import os
import sqlite3
import tempfile
import pytest

from app.audit.ledger import AuditLedgerService
from app.audit.verification import AuditVerifier
from app.database.models import CREATE_AUDIT_EVENTS_TABLE_SQL
from app.database.repositories.audit_repository import AuditRepository


@pytest.fixture
def isolated_audit_env():
    """Setup isolated SQLite database for live audit ledger and tampering verification."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "live_audit_test.db")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(CREATE_AUDIT_EVENTS_TABLE_SQL)

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
        ledger = AuditLedgerService(audit_repo=repo)
        verifier = AuditVerifier(audit_repo=repo)
        yield ledger, verifier, repo, db_path

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_live_audit_chain_and_tamper_detection(isolated_audit_env):
    """Integration test: record live audit events, verify VALID chain, tamper directly in SQLite, and verify TAMPERED detection."""
    ledger, verifier, repo, db_path = isolated_audit_env
    accn = "0000320193-26-000026"

    # 1. Record series of realistic audit events across phases
    evt1 = ledger.record_event(
        event_type="WORKFLOW_STARTED",
        actor="system",
        payload={"thread_id": "thread_live_001", "accession": accn},
        accession_number=accn,
        workflow_id="thread_live_001",
    )
    evt2 = ledger.record_event(
        event_type="FACTS_EXTRACTED",
        actor="arelle_parser",
        payload={"metrics_count": 10, "doc_hash": "58c72ba42db6..."},
        accession_number=accn,
        workflow_id="thread_live_001",
    )
    evt3 = ledger.record_event(
        event_type="REVIEW_DECISION_RECORDED",
        actor="lead_auditor_jane",
        payload={
            "metric_id": "stockholders_equity",
            "decision": "CORRECTED",
            "original_value": 73733000000.0,
            "corrected_value": 112093000000.0,
            "comment": "Certified equity line item from Note 12.",
        },
        accession_number=accn,
        workflow_id="thread_live_001",
        metric_id="stockholders_equity",
    )
    evt4 = ledger.record_event(
        event_type="WORKFLOW_COMPLETED",
        actor="system",
        payload={"final_status": "COMPLETED", "review_round": 1},
        accession_number=accn,
        workflow_id="thread_live_001",
    )

    # 2. Verify intact chain
    v_clean = verifier.verify_chain()
    assert v_clean.is_valid is True
    assert v_clean.status == "VALID"
    assert v_clean.total_events == 4
    assert v_clean.latest_event_hash == evt4.event_hash
    assert v_clean.first_tampered_event_id is None

    # Export checkpoint
    cp = verifier.export_checkpoint()
    assert cp["is_valid"] is True
    assert cp["status"] == "VALID"

    # 3. Simulate malicious tampering: directly alter historical event #3 payload in SQLite database
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE audit_events 
            SET payload_json = '{"comment":"Certified equity line item from Note 12.","corrected_value":99999999999.0,"decision":"CORRECTED","metric_id":"stockholders_equity","original_value":73733000000.0}'
            WHERE sequence_num = 3;
            """
        )
        conn.commit()

    # 4. Re-run verification: MUST detect tampering at event #3!
    v_tampered = verifier.verify_chain()
    assert v_tampered.is_valid is False
    assert v_tampered.status == "TAMPERED"
    assert v_tampered.first_tampered_sequence == 3
    assert v_tampered.first_tampered_event_id == evt3.event_id
    assert "Cryptographic hash mismatch" in v_tampered.failure_reason
    assert "payload or timestamp was altered" in v_tampered.failure_reason

