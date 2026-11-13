from typing import Any, Dict, List, Optional, TypedDict


class ReviewRequirement(TypedDict, total=False):
    required: bool
    reasons: List[str]
    escalated_metrics: List[str]
    validation_failures: List[str]


class ReviewDecision(TypedDict, total=False):
    decision: str  # 'APPROVED', 'REJECTED', 'CORRECTED'
    reviewer_id: str
    decision_notes: str
    decided_at: str
    corrected_values: Optional[Dict[str, float]]


class FilingWorkflowState(TypedDict, total=False):
    # Workflow Identifiers
    workflow_id: str
    thread_id: str
    accession_number: str
    cik: str

    # Workflow Execution State
    current_stage: str  # 'init', 'retrieve', 'extract', 'score', 'validate', 'review', 'completed', 'failed'
    workflow_status: str  # 'RUNNING', 'PAUSED_FOR_REVIEW', 'COMPLETED', 'FAILED'

    # Domain Results
    filing_metadata: Optional[Dict[str, Any]]
    retrieval_result: Optional[Dict[str, Any]]
    extraction_result: Optional[Dict[str, Any]]
    quality_scores: Optional[Dict[str, Any]]
    validation_results: Optional[Dict[str, Any]]

    # Review & Escalation
    review_requirements: Optional[ReviewRequirement]
    review_decisions: Optional[ReviewDecision]

    # Diagnostics & Traceability
    errors: List[str]
    execution_log: List[str]
    created_at: str
    updated_at: str

