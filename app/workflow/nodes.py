import datetime
import logging
from typing import Any, Dict, List, Optional

from langgraph.types import interrupt

from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.reconciliation_repository import ReconciliationRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.database.repositories.xbrl_fact_repository import XBRLFactRepository
from app.extraction.metric_extractor import MetricExtractor
from app.extraction.reconciliation_service import CrossSourceReconciliationService
from app.extraction.semantic_mapping import SemanticMapper
from app.extraction.xbrl_parser import InlineXBRLParser
from app.scoring.quality_score import ConfidenceScoringEngine
from app.sec.client import SECClient
from app.sec.filing_download import FilingDownloader
from app.sec.filing_index import FilingIndexResolver
from app.sec.submissions import SubmissionsManager
from app.validation.engine import FinancialValidationEngine
from app.workflow.state import FilingWorkflowState, ReviewDecision, ReviewRequirement

logger = logging.getLogger("filingguard.workflow.nodes")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def retrieve_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 1: Retrieve official SEC filing metadata and primary document."""
    state.setdefault("execution_log", [])
    state.setdefault("errors", [])
    state["current_stage"] = "retrieve"
    state["workflow_status"] = "RUNNING"
    state["updated_at"] = _now_iso()

    accn = state["accession_number"]
    cik = state.get("cik")

    try:
        filing_repo = FilingRepository()
        doc_repo = DocumentRepository()

        filing = filing_repo.get_by_accession(accn)
        if not filing and cik:
            sec_client = SECClient()
            sub_mgr = SubmissionsManager(client=sec_client)
            resolver = FilingIndexResolver(client=sec_client)

            submissions_data = sub_mgr.fetch_submissions(cik)
            filing = sub_mgr.select_latest_10k(submissions_data)

            if filing and filing.accession_number == accn:
                filing = resolver.resolve_primary_document_url(filing)
                filing_repo.save(filing)

        if not filing:
            err = f"Filing metadata for accession '{accn}' could not be located in database or retrieved from SEC."
            state["errors"].append(err)
            state["workflow_status"] = "FAILED"
            state["execution_log"].append(f"[{_now_iso()}] RETRIEVE FAILED: {err}")
            return state

        state["filing_metadata"] = {
            "accession_number": filing.accession_number,
            "cik": filing.cik,
            "company_name": filing.company_name,
            "ticker": filing.ticker,
            "form_type": filing.form_type,
            "report_period": filing.report_period,
            "primary_document": filing.primary_document,
            "primary_doc_url": filing.primary_doc_url,
        }

        # Check primary document download
        doc = doc_repo.get_by_accession(accn)
        if not doc and filing.primary_doc_url:
            sec_client = SECClient()
            dl_mgr = FilingDownloader(client=sec_client)
            doc = dl_mgr.download_filing(filing)
            doc_repo.save_downloaded_document(doc)

        state["retrieval_result"] = {
            "status": "success",
            "document_path": doc.local_path if doc else None,
            "sha256_hash": doc.sha256_hash if doc else None,
            "file_size_bytes": doc.file_size_bytes if doc else None,
        }
        state["execution_log"].append(f"[{_now_iso()}] RETRIEVE: Filing {accn} resolved successfully.")

    except Exception as e:
        logger.error(f"Error in retrieve_node for {accn}: {e}", exc_info=True)
        state["errors"].append(f"Retrieve stage error: {str(e)}")
        state["workflow_status"] = "FAILED"
        state["execution_log"].append(f"[{_now_iso()}] RETRIEVE ERROR: {str(e)}")

    return state


def extract_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 2: Extract Company Facts, Inline XBRL, and execute cross-source reconciliation."""
    state["current_stage"] = "extract"
    state["updated_at"] = _now_iso()
    accn = state["accession_number"]
    cik = state.get("cik") or state.get("filing_metadata", {}).get("cik")

    try:
        fact_repo = FactRepository()
        xbrl_repo = XBRLFactRepository()
        doc_repo = DocumentRepository()

        # 1. Company facts
        facts = fact_repo.get_selected_facts_by_accession(accn)
        if not facts and cik:
            coordinator = MetricExtractor()
            coordinator.extract_metrics_for_filing(
                cik,
                accession_number=accn,
            )
            facts = fact_repo.get_selected_facts_by_accession(accn)

        # 2. iXBRL facts
        xbrl_facts = xbrl_repo.get_facts_by_accession(accn)
        doc = doc_repo.get_by_accession(accn)
        if not xbrl_facts and doc:
            parser = InlineXBRLParser()
            parsed, parsing_summary = parser.parse_document(
                local_file_path=doc.local_path,
                accession_number=accn,
                source_doc_hash=doc.sha256_hash,
                source_url=doc.source_url,
            )
            if not parsed:
                state["execution_log"].append(
                    f"[{_now_iso()}] EXTRACT WARNING: Inline XBRL parsing produced no facts "
                    f"({parsing_summary.total_facts} parsed)."
                )
            if parsed:
                xbrl_repo.save_facts(parsed)
                xbrl_facts = parsed

        # 3. Cross-source reconciliation
        recon_service = CrossSourceReconciliationService()
        recons = recon_service.reconcile_facts_for_filing(
            accession_number=accn,
            cik=cik or "",
            company_facts=facts,
            ixbrl_facts=xbrl_facts,
        )
        recon_repo = ReconciliationRepository()
        recon_repo.save_reconciliations(recons)

        # 4. Semantic mapping for custom tags
        if xbrl_facts:
            mapper = SemanticMapper()
            candidates = mapper.extract_custom_candidates_from_facts(
                accession_number=accn,
                parsed_facts=xbrl_facts,
            )
            recon_repo.save_custom_candidates(candidates)

        state["extraction_result"] = {
            "status": "success",
            "company_facts_count": len(facts),
            "ixbrl_facts_count": len(xbrl_facts),
            "reconciliations_count": len(recons),
        }
        state["execution_log"].append(
            f"[{_now_iso()}] EXTRACT: Extracted {len(facts)} Company Facts, "
            f"{len(xbrl_facts)} iXBRL facts, {len(recons)} reconciliations."
        )

    except Exception as e:
        logger.error(f"Error in extract_node for {accn}: {e}", exc_info=True)
        state["errors"].append(f"Extract stage error: {str(e)}")
        state["workflow_status"] = "FAILED"
        state["execution_log"].append(f"[{_now_iso()}] EXTRACT ERROR: {str(e)}")

    return state


def score_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 3: Execute Phase 6 5-factor confidence scoring engine."""
    state["current_stage"] = "score"
    state["updated_at"] = _now_iso()
    accn = state["accession_number"]

    try:
        engine = ConfidenceScoringEngine()
        filing_score, metric_scores = engine.score_filing(accn)

        state["quality_scores"] = {
            "overall_score": filing_score.overall_score,
            "overall_status": filing_score.overall_status,
            "overall_review_category": filing_score.overall_review_category,
            "metrics_assessed_count": filing_score.metrics_assessed_count,
            "metrics_missing_count": filing_score.metrics_missing_count,
            "critical_metrics_present": filing_score.critical_metrics_present,
            "reduction_reasons": filing_score.reduction_reasons,
        }
        state["execution_log"].append(
            f"[{_now_iso()}] SCORE: Composite score {filing_score.overall_score:.2f} "
            f"({filing_score.overall_status}) - Category: {filing_score.overall_review_category}."
        )
    except Exception as e:
        logger.error(f"Error in score_node for {accn}: {e}", exc_info=True)
        state["errors"].append(f"Score stage error: {str(e)}")
        state["workflow_status"] = "FAILED"
        state["execution_log"].append(f"[{_now_iso()}] SCORE ERROR: {str(e)}")

    return state


def validate_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 4: Execute Phase 7 financial validation rules."""
    state["current_stage"] = "validate"
    state["updated_at"] = _now_iso()
    accn = state["accession_number"]

    try:
        engine = FinancialValidationEngine()
        results = engine.validate_filing(accn)
        val_repo = ValidationRepository()
        summary = val_repo.get_validation_summary(accn)

        failed_rules = [r.rule_name for r in results if r.status == "FAIL"]
        warning_rules = [r.rule_name for r in results if r.status == "WARNING"]

        state["validation_results"] = {
            "total_rules": summary["total_rules"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "warnings": summary["warnings"],
            "not_evaluated": summary["not_evaluated"],
            "failed_rule_names": failed_rules,
            "warning_rule_names": warning_rules,
        }
        state["execution_log"].append(
            f"[{_now_iso()}] VALIDATE: {summary['passed']} passed, {summary['failed']} failed, "
            f"{summary['warnings']} warnings, {summary['not_evaluated']} not evaluated."
        )
    except Exception as e:
        logger.error(f"Error in validate_node for {accn}: {e}", exc_info=True)
        state["errors"].append(f"Validate stage error: {str(e)}")
        state["workflow_status"] = "FAILED"
        state["execution_log"].append(f"[{_now_iso()}] VALIDATE ERROR: {str(e)}")

    return state


def review_routing_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 5: Determine whether human review is required or if auto-pass applies."""
    state["current_stage"] = "review_routing"
    state["updated_at"] = _now_iso()

    scores = state.get("quality_scores") or {}
    vals = state.get("validation_results") or {}

    review_category = scores.get("overall_review_category", "AUTO_PASS")
    reduction_reasons = scores.get("reduction_reasons", [])
    val_failures = vals.get("failed_rule_names", [])
    val_warnings = vals.get("warning_rule_names", [])

    is_review_required = (
        review_category in ("MANDATORY_REVIEW", "REVIEW_RECOMMENDED")
        or len(val_failures) > 0
        or len(val_warnings) > 0
        or not scores.get("critical_metrics_present", True)
    )

    all_reasons = list(reduction_reasons)
    if val_failures:
        all_reasons.append(f"Financial validation failure(s): {', '.join(val_failures)}.")
    if val_warnings:
        all_reasons.append(f"Financial validation warning(s): {', '.join(val_warnings)}.")

    if is_review_required:
        state["review_requirements"] = ReviewRequirement(
            required=True,
            reasons=all_reasons,
            escalated_metrics=[r for r in all_reasons if "Metric" in r],
            validation_failures=val_failures,
        )
        state["workflow_status"] = "PAUSED_FOR_REVIEW"
        state["current_stage"] = "review"
        state["execution_log"].append(
            f"[{_now_iso()}] ROUTING: Escalated to human review queue. Reasons: {len(all_reasons)} trigger(s)."
        )
    else:
        state["review_requirements"] = ReviewRequirement(
            required=False,
            reasons=[],
            escalated_metrics=[],
            validation_failures=[],
        )
        state["current_stage"] = "complete"
        state["execution_log"].append(
            f"[{_now_iso()}] ROUTING: All deterministic gates passed. Auto-pass granted."
        )

    return state


def human_review_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 6: Pause workflow using LangGraph interrupt() and wait for auditor review command."""
    accn = state["accession_number"]
    reqs = state.get("review_requirements", {})

    interrupt_payload = {
        "accession_number": accn,
        "workflow_id": state.get("workflow_id"),
        "thread_id": state.get("thread_id"),
        "review_reasons": reqs.get("reasons", []),
        "validation_failures": reqs.get("validation_failures", []),
        "prompt": "Filing requires auditor review. Please inspect evidence and submit decision (APPROVED/REJECTED/CORRECTED).",
    }

    # Pause execution until resumed with Command(resume=decision_payload)
    decision_data = interrupt(interrupt_payload)

    # Process decision on resume
    if isinstance(decision_data, dict):
        decision_val = decision_data.get("decision", "APPROVED")
        reviewer_id = decision_data.get("reviewer_id", "auditor")
        notes = decision_data.get("decision_notes", "Reviewed and confirmed.")
        corrections = decision_data.get("corrected_values")
    else:
        decision_val = str(decision_data)
        reviewer_id = "auditor"
        notes = "Reviewed."
        corrections = None

    state["review_decisions"] = ReviewDecision(
        decision=decision_val.upper(),
        reviewer_id=reviewer_id,
        decision_notes=notes,
        decided_at=_now_iso(),
        corrected_values=corrections,
    )
    state["current_stage"] = "reviewed"
    state["execution_log"].append(
        f"[{_now_iso()}] HUMAN REVIEW: Resumed with decision '{decision_val.upper()}' by {reviewer_id}. Notes: {notes}"
    )

    return state


def complete_node(state: FilingWorkflowState) -> FilingWorkflowState:
    """Node 7: Finalize workflow execution and set terminal status."""
    state["current_stage"] = "completed"
    state["updated_at"] = _now_iso()

    if state.get("errors"):
        state["workflow_status"] = "FAILED"
        state["execution_log"].append(f"[{_now_iso()}] WORKFLOW TERMINATED WITH ERRORS.")
    elif (state.get("review_decisions") or {}).get("decision") == "REJECTED":
        state["workflow_status"] = "REJECTED"
        state["execution_log"].append(f"[{_now_iso()}] WORKFLOW COMPLETED: REJECTED BY REVIEWER.")
    else:
        state["workflow_status"] = "COMPLETED"
        state["execution_log"].append(f"[{_now_iso()}] WORKFLOW COMPLETED SUCCESSFULLY.")

    return state
