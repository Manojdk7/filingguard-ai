import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app

client = TestClient(app)


def test_start_workflow_invalid_input():
    response = client.post("/workflows/start", json={"accession_number": "   "})
    assert response.status_code == 400
    assert "Valid accession number" in response.json()["detail"]


def test_get_workflow_status_not_found():
    response = client.get("/workflows/non-existent-thread-000/status")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_workflow_result_not_found():
    response = client.get("/workflows/non-existent-thread-000/result")
    assert response.status_code == 404


def test_submit_review_invalid_thread():
    response = client.post(
        "/workflows/non-existent-thread-000/review",
        json={"decision": "APPROVED", "decision_notes": "All good"},
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_workflow_start_api_success():
    with patch("app.api.routes.workflows.WorkflowService") as mock_service_cls:
        mock_service = MagicMock()
        mock_service.start_workflow.return_value = (
            "thread_mock_001",
            {
                "workflow_id": "wf_mock_001",
                "thread_id": "thread_mock_001",
                "accession_number": "0000320193-26-000026",
                "current_stage": "completed",
                "workflow_status": "COMPLETED",
                "review_requirements": {"required": False},
                "errors": [],
                "execution_log": ["Complete"],
            },
        )
        mock_service.get_workflow_state.return_value = {
            "thread_id": "thread_mock_001",
            "is_paused_for_review": False,
            "values": {},
        }
        mock_service_cls.return_value = mock_service

        response = client.post(
            "/workflows/start",
            json={"accession_number": "0000320193-26-000026", "cik": "0000320193"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == "thread_mock_001"
        assert data["workflow_status"] == "COMPLETED"
        assert data["is_paused_for_review"] is False

