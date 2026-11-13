import datetime
import logging
from typing import Any, Dict, Optional, Tuple
from langgraph.types import Command

from app.workflow.checkpointer import get_checkpointer
from app.workflow.graph import compile_workflow_graph
from app.workflow.state import FilingWorkflowState

logger = logging.getLogger("filingguard.workflow.resume")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class WorkflowService:
    """Service orchestrating execution, status query, and human review resumption of LangGraph audit workflows."""

    def __init__(self, checkpointer=None):
        self.checkpointer = checkpointer or get_checkpointer()
        self.graph = compile_workflow_graph(checkpointer=self.checkpointer)

    def start_workflow(
        self,
        accession_number: str,
        cik: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Tuple[str, FilingWorkflowState]:
        """Initiate an end-to-end audit workflow for an accession number."""
        clean_accn = accession_number.strip()
        t_id = thread_id or f"thread_{clean_accn}"
        wf_id = f"wf_{clean_accn}_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"

        initial_state: FilingWorkflowState = {
            "workflow_id": wf_id,
            "thread_id": t_id,
            "accession_number": clean_accn,
            "cik": cik or "",
            "current_stage": "init",
            "workflow_status": "RUNNING",
            "filing_metadata": None,
            "retrieval_result": None,
            "extraction_result": None,
            "quality_scores": None,
            "validation_results": None,
            "review_requirements": None,
            "review_decisions": None,
            "errors": [],
            "execution_log": [f"[{_now_iso()}] Workflow {wf_id} initialized for accession {clean_accn}."],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }

        config = {"configurable": {"thread_id": t_id}}
        logger.info(f"Starting workflow for accession {clean_accn} on thread {t_id}")

        try:
            from app.audit.ledger import AuditLedgerService
            AuditLedgerService().record_event(
                event_type="WORKFLOW_STARTED",
                actor="system",
                payload={"workflow_id": wf_id, "thread_id": t_id, "accession_number": clean_accn, "cik": cik},
                accession_number=clean_accn,
                workflow_id=t_id,
            )
        except Exception as e:
            logger.debug(f"Audit log skipped: {e}")

        result_state = self.graph.invoke(initial_state, config=config)
        return t_id, result_state

    def get_workflow_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve current checkpoint state and interruption status for a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = self.graph.get_state(config)

        if not state_snapshot or not state_snapshot.values:
            return None

        # Determine if paused for human review
        is_paused = bool(state_snapshot.next) and any("human_review" in step for step in state_snapshot.next)
        interrupt_value = None
        if state_snapshot.tasks:
            for task in state_snapshot.tasks:
                if getattr(task, "interrupts", None):
                    interrupt_value = [i.value for i in task.interrupts]

        return {
            "thread_id": thread_id,
            "values": state_snapshot.values,
            "next_steps": list(state_snapshot.next),
            "is_paused_for_review": is_paused,
            "interrupt_details": interrupt_value,
        }

    def resume_workflow(
        self,
        thread_id: str,
        decision: str,
        reviewer_id: str = "auditor",
        decision_notes: str = "",
        corrected_values: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Resume an interrupted workflow thread with an auditor review decision."""
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = self.graph.get_state(config)

        if not state_snapshot or not state_snapshot.values:
            raise ValueError(f"Workflow thread '{thread_id}' not found.")

        is_paused = bool(state_snapshot.next) and any("human_review" in step for step in state_snapshot.next)
        if not is_paused:
            raise ValueError(f"Workflow thread '{thread_id}' is not currently paused for review.")

        resume_payload = {
            "decision": decision.upper(),
            "reviewer_id": reviewer_id,
            "decision_notes": decision_notes or "Auditor decision submitted.",
            "corrected_values": corrected_values,
        }

        logger.info(f"Resuming thread {thread_id} with decision {decision.upper()} by {reviewer_id}")
        try:
            from app.audit.ledger import AuditLedgerService
            AuditLedgerService().record_event(
                event_type="WORKFLOW_RESUMED",
                actor=reviewer_id,
                payload={"thread_id": thread_id, "decision": decision.upper(), "notes": decision_notes},
                workflow_id=thread_id,
            )
        except Exception as e:
            logger.debug(f"Audit log skipped: {e}")

        resumed_state = self.graph.invoke(Command(resume=resume_payload), config=config)
        return resumed_state

