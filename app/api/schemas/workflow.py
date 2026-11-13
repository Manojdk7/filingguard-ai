from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StartWorkflowRequest(BaseModel):
    accession_number: str = Field(..., description="SEC 10-K accession number")
    cik: Optional[str] = Field(None, description="Optional 10-digit CIK")
    thread_id: Optional[str] = Field(None, description="Optional custom thread ID")


class SubmitReviewRequest(BaseModel):
    decision: str = Field(..., description="APPROVED, REJECTED, or CORRECTED")
    reviewer_id: Optional[str] = Field("auditor", description="Reviewer identifier")
    decision_notes: Optional[str] = Field("Auditor review submitted.", description="Mandatory audit notes")
    corrected_values: Optional[Dict[str, float]] = Field(None, description="Optional map of metric corrections")


class WorkflowStatusResponse(BaseModel):
    thread_id: str
    workflow_id: Optional[str] = None
    accession_number: Optional[str] = None
    current_stage: Optional[str] = None
    workflow_status: Optional[str] = None
    is_paused_for_review: bool = False
    review_requirements: Optional[Dict[str, Any]] = None
    review_decisions: Optional[Dict[str, Any]] = None
    quality_scores: Optional[Dict[str, Any]] = None
    validation_results: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    execution_log: List[str] = []
    updated_at: Optional[str] = None

