import uuid
import pytest

from app.api.schemas.review import SubmitReviewRequest
from app.database.repositories.review_repository import ReviewRepository
from app.review.service import ReviewService


def test_live_apple_review_workflow():
    """Live integration test: execute complete review loop against real Apple Inc. 10-K filing."""
    accession_number = "0000320193-26-000026"
    service = ReviewService()
    repo = ReviewRepository()

    # 1. Fetch review queue for Apple
    queue = service.get_review_queue(accession_number=accession_number)
    assert len(queue) >= 10

    rev_item = next((item for item in queue if item.metric_id == "revenue"), None)
    assert rev_item is not None
    assert rev_item.extracted_value == 478834000000.0
    assert rev_item.unit == "USD"
    assert rev_item.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert rev_item.quality_score is not None
    assert rev_item.quality_score >= 0.95

    # 2. Submit human review approval with idempotency key
    idemp_key = f"live_test_{uuid.uuid4().hex[:12]}"
    req = SubmitReviewRequest(
        accession_number=accession_number,
        metric_id="revenue",
        decision="APPROVED",
        reviewer_id="auditor_lead_live_test",
        comment="Live integration test: certified revenue matching note 2 breakdown.",
        idempotency_key=idemp_key,
    )

    res1 = service.submit_review(req)
    assert res1.decision == "APPROVED"
    assert res1.reviewer_id == "auditor_lead_live_test"
    assert res1.original_value == 478834000000.0
    assert res1.is_duplicate is False

    # 3. Query database directly to verify persistence
    saved = repo.get_by_review_id(res1.review_id)
    assert saved is not None
    assert saved.accession_number == accession_number
    assert saved.decision == "APPROVED"
    assert saved.idempotency_key == idemp_key

    # 4. Submit duplicate review with same idempotency key
    res2 = service.submit_review(req)
    assert res2.is_duplicate is True
    assert res2.review_id == res1.review_id

    # 5. Verify review history includes the record
    history = repo.get_reviews_by_accession(accession_number)
    matching = [h for h in history if h.idempotency_key == idemp_key]
    assert len(matching) == 1
