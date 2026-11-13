from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.audit.verification import VerificationResult
from app.database.repositories.audit_repository import AuditEventRecord
from app.main import app

client = TestClient(app)


def test_get_audit_events_endpoint():
    """Test GET /audit/events returns 200 and list of audit events."""
    with patch("app.api.routes.audit.AuditLedgerService") as mock_service_cls:
        mock_service = MagicMock()
        mock_service.get_events.return_value = [
            AuditEventRecord(
                id=1,
                event_id="evt_test_001",
                sequence_num=1,
                workflow_id="wf_001",
                accession_number="0000320193-26-000026",
                metric_id="revenue",
                event_type="REVIEW_DECISION_RECORDED",
                actor="auditor_jane",
                payload={"decision": "APPROVED"},
                previous_hash="0" * 64,
                event_hash="a" * 64,
                created_at="2026-01-01T00:00:00Z",
                signature="s" * 64,
            )
        ]
        mock_service_cls.return_value = mock_service

        response = client.get("/audit/events?accession_number=0000320193-26-000026")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["event_id"] == "evt_test_001"
        assert data[0]["event_type"] == "REVIEW_DECISION_RECORDED"
        assert data[0]["actor"] == "auditor_jane"


def test_verify_audit_ledger_valid():
    """Test GET /audit/verify returns 200 with status VALID when chain is intact."""
    with patch("app.api.routes.audit.AuditVerifier") as mock_verifier_cls:
        mock_verifier = MagicMock()
        mock_verifier.verify_chain.return_value = VerificationResult(
            is_valid=True,
            status="VALID",
            total_events=5,
            latest_event_hash="c" * 64,
            verified_at="2026-01-01T00:00:00Z",
        )
        mock_verifier_cls.return_value = mock_verifier

        response = client.get("/audit/verify")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["status"] == "VALID"
        assert data["total_events"] == 5


def test_verify_audit_ledger_tampered():
    """Test GET /audit/verify returns 200 with status TAMPERED when tampering detected."""
    with patch("app.api.routes.audit.AuditVerifier") as mock_verifier_cls:
        mock_verifier = MagicMock()
        mock_verifier.verify_chain.return_value = VerificationResult(
            is_valid=False,
            status="TAMPERED",
            total_events=3,
            first_tampered_event_id="evt_002",
            first_tampered_sequence=2,
            failure_reason="Cryptographic hash mismatch: payload or timestamp was altered!",
            verified_at="2026-01-01T00:00:00Z",
        )
        mock_verifier_cls.return_value = mock_verifier

        response = client.get("/audit/verify")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert data["status"] == "TAMPERED"
        assert data["first_tampered_sequence"] == 2
        assert "hash mismatch" in data["failure_reason"].lower()


def test_export_checkpoint_endpoint():
    """Test GET /audit/export returns 200 and signed checkpoint data."""
    with patch("app.api.routes.audit.AuditVerifier") as mock_verifier_cls:
        mock_verifier = MagicMock()
        mock_verifier.export_checkpoint.return_value = {
            "checkpoint_type": "FILINGGUARD_AUDIT_LEDGER_CHECKPOINT",
            "version": "1.0.0",
            "status": "VALID",
            "is_valid": True,
            "total_events": 10,
            "latest_event_hash": "d" * 64,
            "signature": "sig" * 20,
            "verified_at": "2026-01-01T00:00:00Z",
            "accession_number": None,
        }
        mock_verifier_cls.return_value = mock_verifier

        response = client.get("/audit/export")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "VALID"
        assert data["total_events"] == 10
        assert "signature" in data

