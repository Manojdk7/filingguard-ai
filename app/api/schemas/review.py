from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReviewQueueItemResponse(BaseModel):
    """Represents a financial metric or filing item pending or escalated for human review."""
    accession_number: str
    cik: str
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    report_period: Optional[str] = None
    form_type: Optional[str] = None
    metric_id: str
    canonical_name: str
    extracted_value: Optional[float] = None
    unit: Optional[str] = None
    concept: Optional[str] = None
    taxonomy: Optional[str] = None
    quality_score: Optional[float] = None
    quality_status: Optional[str] = None
    review_category: Optional[str] = None
    evidence_refs: Dict[str, Any] = Field(default_factory=dict)
    source_excerpt: Optional[str] = None
    flagged_reason: Optional[str] = None
    validation_status: Optional[str] = None
    validation_explanation: Optional[str] = None
    escalation_reasons: List[str] = Field(default_factory=list)
    review_status: str = "PENDING"  # 'PENDING', 'APPROVED', 'CORRECTED', 'REJECTED'
    thread_id: Optional[str] = None


class SubmitReviewRequest(BaseModel):
    """Payload for submitting a human review action (Approve, Correct, Reject)."""
    accession_number: str
    metric_id: Optional[str] = None
    decision: str  # 'APPROVED', 'CORRECTED', 'REJECTED'
    reviewer_id: str
    comment: str
    corrected_value: Optional[float] = None
    unit: Optional[str] = None
    evidence_used: Optional[str] = None
    idempotency_key: Optional[str] = None
    thread_id: Optional[str] = None


class SubmitReviewResponse(BaseModel):
    """Result of human review decision submission, including validation comparison and audit trail info."""
    review_id: str
    accession_number: str
    thread_id: Optional[str] = None
    metric_id: Optional[str] = None
    canonical_name: Optional[str] = None
    review_round: int = 1
    reviewer_id: str
    decision: str
    original_value: Optional[float] = None
    corrected_value: Optional[float] = None
    unit: Optional[str] = None
    comment: str
    evidence_used: Optional[str] = None
    idempotency_key: str
    is_duplicate: bool = False
    previous_validation_status: Optional[str] = None
    new_validation_status: Optional[str] = None
    revalidation_summary: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None

