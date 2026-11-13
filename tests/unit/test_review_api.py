from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.schemas.review import ReviewQueueItemResponse, SubmitReviewResponse
from app.database.repositories.review_repository import ReviewRecord
from app.main import app

client = TestClient(app)


def test_get_review_queue_endpoint():
    """Test GET /reviews/queue returns 200 and list of queue items."""
    with patch("app.api.routes.reviews.ReviewService") as mock_service_cls:
        mock_service = MagicMock()
        mock_service.get_review_queue.return_value = [
            ReviewQueueItemResponse(
                accession_number="0000320193-26-000026",
                cik="0000320193",
                company_name="Apple Inc.",
                ticker="AAPL",
                metric_id="revenue",
                canonical_name="Revenue",
                extracted_value=391035000000.0,
                unit="USD",
                quality_score=0.98,
                quality_status="HIGH",
                review_category="AUTO_PASS",
                review_status="PENDING",
            )
        ]
        mock_service_cls.return_value = mock_service

        response = client.get("/reviews/queue?accession_number=0000320193-26-000026")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["metric_id"] == "revenue"
        assert data[0]["canonical_name"] == "Revenue"


def test_get_review_history_empty_accession():
    """Test GET /reviews/history with whitespace accession returns 400."""
    response = client.get("/reviews/history/%20%20")
    assert response.status_code == 400


def test_get_review_history_success():
    """Test GET /reviews/history/{accession_number} returns review history records."""
    with patch("app.api.routes.reviews.ReviewRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_reviews_by_accession.return_value = [
            ReviewRecord(
                id=1,
                review_id="rev_test_001",
                accession_number="0000320193-26-000026",
                metric_id="stockholders_equity",
                canonical_name="Stockholders Equity",
                review_round=1,
                reviewer_id="auditor_jane",
                decision="CORRECTED",
                original_value=50000000.0,
                corrected_value=60000000.0,
                unit="USD",
                comment="Updated equity line",
                idempotency_key="idemp_001",
                created_at="2026-01-01T00:00:00Z",
            )
        ]
        mock_repo_cls.return_value = mock_repo

        response = client.get("/reviews/history/0000320193-26-000026")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["review_id"] == "rev_test_001"
        assert data[0]["decision"] == "CORRECTED"
        assert data[0]["original_value"] == 50000000.0
        assert data[0]["corrected_value"] == 60000000.0


def test_submit_review_validation_errors():
    """Test POST /reviews/submit returns 400 on invalid input parameters."""
    # Automated actor
    res1 = client.post(
        "/reviews/submit",
        json={
            "accession_number": "test-accn",
            "metric_id": "revenue",
            "decision": "APPROVED",
            "reviewer_id": "ai",
            "comment": "Bot approved",
        },
    )
    assert res1.status_code == 400
    assert "automated entity" in res1.json()["detail"].lower()

    # Invalid decision
    res2 = client.post(
        "/reviews/submit",
        json={
            "accession_number": "test-accn",
            "metric_id": "revenue",
            "decision": "MAYBE",
            "reviewer_id": "auditor_real",
            "comment": "Unsure",
        },
    )
    assert res2.status_code == 400
    assert "Invalid decision" in res2.json()["detail"]

    # Empty comment
    res3 = client.post(
        "/reviews/submit",
        json={
            "accession_number": "test-accn",
            "metric_id": "revenue",
            "decision": "APPROVED",
            "reviewer_id": "auditor_real",
            "comment": "   ",
        },
    )
    assert res3.status_code == 400
    assert "comment" in res3.json()["detail"].lower()

    # Corrected without corrected_value
    res4 = client.post(
        "/reviews/submit",
        json={
            "accession_number": "test-accn",
            "metric_id": "revenue",
            "decision": "CORRECTED",
            "reviewer_id": "auditor_real",
            "comment": "Correction comment",
            "corrected_value": None,
        },
    )
    assert res4.status_code == 400
    assert "corrected_value" in res4.json()["detail"]


def test_submit_review_success_and_idempotency():
    """Test POST /reviews/submit records review and safely returns duplicate on replay."""
    with patch("app.api.routes.reviews.ReviewService") as mock_service_cls:
        mock_service = MagicMock()
        mock_service.submit_review.side_effect = [
            SubmitReviewResponse(
                review_id="rev_apple_rev_001",
                accession_number="0000320193-26-000026",
                metric_id="revenue",
                canonical_name="Revenue",
                review_round=1,
                reviewer_id="lead_auditor",
                decision="APPROVED",
                original_value=391035000000.0,
                comment="Confirmed with revenue footnote.",
                idempotency_key="idemp_rev_test_999",
                is_duplicate=False,
                created_at="2026-01-01T00:00:00Z",
            ),
            SubmitReviewResponse(
                review_id="rev_apple_rev_001",
                accession_number="0000320193-26-000026",
                metric_id="revenue",
                canonical_name="Revenue",
                review_round=1,
                reviewer_id="lead_auditor",
                decision="APPROVED",
                original_value=391035000000.0,
                comment="Confirmed with revenue footnote.",
                idempotency_key="idemp_rev_test_999",
                is_duplicate=True,
                created_at="2026-01-01T00:00:00Z",
            ),
        ]
        mock_service_cls.return_value = mock_service

        payload = {
            "accession_number": "0000320193-26-000026",
            "metric_id": "revenue",
            "decision": "APPROVED",
            "reviewer_id": "lead_auditor",
            "comment": "Confirmed with revenue footnote.",
            "idempotency_key": "idemp_rev_test_999",
        }

        # First submission
        res1 = client.post("/reviews/submit", json=payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["review_id"] == "rev_apple_rev_001"
        assert data1["is_duplicate"] is False

        # Replay duplicate submission
        res2 = client.post("/reviews/submit", json=payload)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["review_id"] == "rev_apple_rev_001"
        assert data2["is_duplicate"] is True

