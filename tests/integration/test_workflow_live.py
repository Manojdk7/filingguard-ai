import pytest
from app.workflow.resume import WorkflowService


def test_live_apple_workflow_execution():
    """Integration test: execute end-to-end LangGraph workflow for real Apple Inc. 10-K filing."""
    accession_number = "0000320193-26-000026"
    service = WorkflowService()
    thread_id = f"thread_live_apple_test"

    t_id, final_state = service.start_workflow(
        accession_number=accession_number,
        cik="0000320193",
        thread_id=thread_id,
    )

    assert t_id == thread_id
    assert final_state["accession_number"] == accession_number
    # Warnings (YoY variance / Segment breakdown) route to human review pause
    assert final_state["workflow_status"] == "PAUSED_FOR_REVIEW"
    assert final_state["current_stage"] == "review"

    # Verify quality scoring results are embedded
    quality = final_state.get("quality_scores")
    assert quality is not None
    assert quality["overall_score"] >= 0.95
    assert quality["overall_status"] == "HIGH"
    assert quality["critical_metrics_present"] is True

    # Verify financial validation results are embedded
    val = final_state.get("validation_results")
    assert val is not None
    assert val["total_rules"] >= 12
    assert val["failed"] == 0
    assert len(val.get("warning_rule_names", [])) > 0

    # Verify execution log captures stage progression
    log = final_state.get("execution_log", [])
    assert any("RETRIEVE" in entry for entry in log)
    assert any("EXTRACT" in entry for entry in log)
    assert any("SCORE" in entry for entry in log)
    assert any("VALIDATE" in entry for entry in log)

    # Verify state can be queried directly from SQLite checkpointer
    status_snapshot = service.get_workflow_state(thread_id)
    assert status_snapshot is not None
    assert status_snapshot["values"]["workflow_status"] == "PAUSED_FOR_REVIEW"
    assert status_snapshot["is_paused_for_review"] is True

    # Resume the workflow with auditor decision
    resumed_state = service.resume_workflow(
        thread_id=thread_id,
        decision="APPROVE",
        reviewer_id="auditor_live",
        decision_notes="Approved in live test",
    )
    assert resumed_state["workflow_status"] == "COMPLETED"
    assert resumed_state["current_stage"] == "completed"
    assert any("COMPLETED" in entry for entry in resumed_state.get("execution_log", []))

