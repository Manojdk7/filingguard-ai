import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas.review import (
    ReviewQueueItemResponse,
    SubmitReviewRequest,
    SubmitReviewResponse,
)
from app.database.repositories.review_repository import ReviewRepository
from app.review.service import ReviewService

logger = logging.getLogger("filingguard.api.reviews")

router = APIRouter(prefix="/reviews", tags=["Human Review & Auditor Interface"])


@router.get(
    "/queue",
    response_model=List[ReviewQueueItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Get pending human review queue items",
)
def get_review_queue_endpoint(
    accession_number: Optional[str] = Query(None, description="Optional filter by filing accession number"),
) -> List[ReviewQueueItemResponse]:
    """Retrieve items requiring human review, with evidence locators, quality factors, and validation alerts."""
    try:
        service = ReviewService()
        clean_accn = accession_number.strip() if accession_number else None
        return service.get_review_queue(clean_accn)
    except Exception as e:
        logger.error(f"Error fetching review queue: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve review queue: {str(e)}",
        )


@router.get(
    "/history/{accession_number}",
    response_model=List[SubmitReviewResponse],
    status_code=status.HTTP_200_OK,
    summary="Get human review history for a filing",
)
def get_review_history_endpoint(accession_number: str) -> List[SubmitReviewResponse]:
    """Retrieve past human auditor reviews, decisions, and corrections for a filing."""
    clean_accn = accession_number.strip()
    if not clean_accn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid accession number is required.",
        )

    try:
        repo = ReviewRepository()
        records = repo.get_reviews_by_accession(clean_accn)
        return [
            SubmitReviewResponse(
                review_id=r.review_id,
                accession_number=r.accession_number,
                thread_id=r.thread_id,
                metric_id=r.metric_id,
                canonical_name=r.canonical_name,
                review_round=r.review_round,
                reviewer_id=r.reviewer_id,
                decision=r.decision,
                original_value=r.original_value,
                corrected_value=r.corrected_value,
                unit=r.unit,
                comment=r.comment,
                evidence_used=r.evidence_used,
                idempotency_key=r.idempotency_key or "",
                is_duplicate=False,
                previous_validation_status=r.previous_validation_status,
                new_validation_status=r.new_validation_status,
                created_at=r.created_at,
            )
            for r in records
        ]
    except Exception as e:
        logger.error(f"Error fetching review history for {clean_accn}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve review history: {str(e)}",
        )


@router.post(
    "/submit",
    response_model=SubmitReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit human auditor review decision (Approve, Correct, Reject)",
)
def submit_review_endpoint(request: SubmitReviewRequest) -> SubmitReviewResponse:
    """Submit a reviewer decision with idempotency guarantee, validation recalculation, and workflow resumption."""
    try:
        service = ReviewService()
        return service.submit_review(request)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error processing review submission: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review processing failure: {str(e)}",
        )

