import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status

from app.api.schemas.workflow import (
    StartWorkflowRequest,
    SubmitReviewRequest,
    WorkflowStatusResponse,
)
from app.workflow.resume import WorkflowService

logger = logging.getLogger("filingguard.api.workflows")

router = APIRouter(prefix="/workflows", tags=["Agentic Workflow (LangGraph)"])


@router.post(
    "/start",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Start an agentic audit workflow for a filing",
)
def start_workflow_endpoint(request: StartWorkflowRequest) -> WorkflowStatusResponse:
    """Initiate the complete end-to-end pipeline (retrieve -> extract -> score -> validate -> review/complete)."""
    clean_accn = request.accession_number.strip()
    if not clean_accn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid accession number is required.",
        )

    try:
        service = WorkflowService()
        thread_id, state = service.start_workflow(
            accession_number=clean_accn,
            cik=request.cik.strip() if request.cik else None,
            thread_id=request.thread_id.strip() if request.thread_id else None,
        )

        status_data = service.get_workflow_state(thread_id)
        is_paused = status_data["is_paused_for_review"] if status_data else False

        return WorkflowStatusResponse(
            thread_id=thread_id,
            workflow_id=state.get("workflow_id"),
            accession_number=state.get("accession_number"),
            current_stage=state.get("current_stage"),
            workflow_status=state.get("workflow_status"),
            is_paused_for_review=is_paused,
            review_requirements=state.get("review_requirements"),
            review_decisions=state.get("review_decisions"),
            quality_scores=state.get("quality_scores"),
            validation_results=state.get("validation_results"),
            errors=state.get("errors", []),
            execution_log=state.get("execution_log", []),
            updated_at=state.get("updated_at"),
        )
    except Exception as e:
        logger.error(f"Error starting workflow for {clean_accn}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failure: {str(e)}",
        )


@router.get(
    "/{thread_id}/status",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get workflow execution status and review state",
)
def get_workflow_status_endpoint(thread_id: str) -> WorkflowStatusResponse:
    """Query current stage, review requirements, and execution log for a workflow thread."""
    clean_thread = thread_id.strip()
    service = WorkflowService()
    status_data = service.get_workflow_state(clean_thread)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow thread '{clean_thread}' not found.",
        )

    values = status_data["values"]
    return WorkflowStatusResponse(
        thread_id=clean_thread,
        workflow_id=values.get("workflow_id"),
        accession_number=values.get("accession_number"),
        current_stage=values.get("current_stage"),
        workflow_status=values.get("workflow_status"),
        is_paused_for_review=status_data["is_paused_for_review"],
        review_requirements=values.get("review_requirements"),
        review_decisions=values.get("review_decisions"),
        quality_scores=values.get("quality_scores"),
        validation_results=values.get("validation_results"),
        errors=values.get("errors", []),
        execution_log=values.get("execution_log", []),
        updated_at=values.get("updated_at"),
    )


@router.get(
    "/{thread_id}/result",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Retrieve full workflow state and audit artifacts",
)
def get_workflow_result_endpoint(thread_id: str) -> Dict[str, Any]:
    """Retrieve the complete typed state payload from durable SQLite checkpoint."""
    clean_thread = thread_id.strip()
    service = WorkflowService()
    status_data = service.get_workflow_state(clean_thread)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow thread '{clean_thread}' not found.",
        )

    return status_data["values"]


@router.post(
    "/{thread_id}/review",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit human auditor review decision and resume workflow",
)
def submit_review_endpoint(thread_id: str, request: SubmitReviewRequest) -> WorkflowStatusResponse:
    """Resume an interrupted workflow by submitting an auditor decision (APPROVED, REJECTED, CORRECTED)."""
    clean_thread = thread_id.strip()
    service = WorkflowService()

    try:
        resumed_state = service.resume_workflow(
            thread_id=clean_thread,
            decision=request.decision,
            reviewer_id=request.reviewer_id or "auditor",
            decision_notes=request.decision_notes or "Reviewed.",
            corrected_values=request.corrected_values,
        )

        status_data = service.get_workflow_state(clean_thread)
        is_paused = status_data["is_paused_for_review"] if status_data else False

        return WorkflowStatusResponse(
            thread_id=clean_thread,
            workflow_id=resumed_state.get("workflow_id"),
            accession_number=resumed_state.get("accession_number"),
            current_stage=resumed_state.get("current_stage"),
            workflow_status=resumed_state.get("workflow_status"),
            is_paused_for_review=is_paused,
            review_requirements=resumed_state.get("review_requirements"),
            review_decisions=resumed_state.get("review_decisions"),
            quality_scores=resumed_state.get("quality_scores"),
            validation_results=resumed_state.get("validation_results"),
            errors=resumed_state.get("errors", []),
            execution_log=resumed_state.get("execution_log", []),
            updated_at=resumed_state.get("updated_at"),
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error resuming workflow thread {clean_thread}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume workflow: {str(e)}",
        )

