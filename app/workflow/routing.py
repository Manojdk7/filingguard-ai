import logging
from typing import Literal
from app.workflow.state import FilingWorkflowState

logger = logging.getLogger("filingguard.workflow.routing")


def route_after_retrieve(state: FilingWorkflowState) -> Literal["extract", "complete"]:
    """Route to extraction if retrieval succeeded, or stop if failed."""
    if state.get("errors") or state.get("workflow_status") == "FAILED":
        logger.warning(f"Workflow {state.get('workflow_id')} routing to complete due to retrieval error.")
        return "complete"
    return "extract"


def route_after_extract(state: FilingWorkflowState) -> Literal["score", "complete"]:
    """Route to confidence scoring if extraction succeeded, or stop if failed."""
    if state.get("errors") or state.get("workflow_status") == "FAILED":
        logger.warning(f"Workflow {state.get('workflow_id')} routing to complete due to extraction error.")
        return "complete"
    return "score"


def route_after_review_routing(state: FilingWorkflowState) -> Literal["human_review", "complete"]:
    """Conditional routing based on deterministic review requirements."""
    if state.get("errors") or state.get("workflow_status") == "FAILED":
        return "complete"

    req = state.get("review_requirements", {})
    if req and req.get("required", False):
        logger.info(f"Workflow {state.get('workflow_id')} routed to human review: {req.get('reasons')}")
        return "human_review"

    logger.info(f"Workflow {state.get('workflow_id')} eligible for auto-pass.")
    return "complete"

