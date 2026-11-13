import datetime
import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional

from app.api.schemas.review import ReviewQueueItemResponse, SubmitReviewRequest, SubmitReviewResponse
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.review_repository import ReviewRecord, ReviewRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.review.idempotency import IdempotencyManager, generate_idempotency_key, validate_idempotency_key
from app.validation.engine import FinancialValidationEngine
from app.workflow.resume import WorkflowService

logger = logging.getLogger("filingguard.review.service")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ReviewService:
    """Service managing the human review loop: queue generation, review validation,

    correction preserving original values, idempotency, and workflow resumption.
    """

    def __init__(
        self,
        review_repo: Optional[ReviewRepository] = None,
        fact_repo: Optional[FactRepository] = None,
        filing_repo: Optional[FilingRepository] = None,
        scoring_repo: Optional[ScoringRepository] = None,
        validation_repo: Optional[ValidationRepository] = None,
        validation_engine: Optional[FinancialValidationEngine] = None,
        workflow_service: Optional[WorkflowService] = None,
        idempotency_mgr: Optional[IdempotencyManager] = None,
    ):
        self.review_repo = review_repo or ReviewRepository()
        self.fact_repo = fact_repo or FactRepository()
        self.filing_repo = filing_repo or FilingRepository()
        self.scoring_repo = scoring_repo or ScoringRepository()
        self.validation_repo = validation_repo or ValidationRepository()
        self.validation_engine = validation_engine or FinancialValidationEngine()
        self.workflow_service = workflow_service or WorkflowService()
        self.idempotency_mgr = idempotency_mgr or IdempotencyManager(self.review_repo)

    def get_review_queue(self, accession_number: Optional[str] = None) -> List[ReviewQueueItemResponse]:
        """Aggregate review queue items across filings or for a target filing.

        Includes extracted facts, quality scores, evidence locators, and validation findings.
        """
        queue_items: List[ReviewQueueItemResponse] = []

        if accession_number:
            filings = [self.filing_repo.get_by_accession(accession_number)]
            filings = [f for f in filings if f is not None]
        else:
            filings = self.filing_repo.get_recent_filings(limit=25)

        for filing in filings:
            accn = filing.accession_number
            cik = filing.cik

            # Get scores and validation results
            scores = self.scoring_repo.get_metric_scores_by_accession(accn)
            scores_by_metric = {s.metric_id: s for s in scores}
            filing_score = self.scoring_repo.get_filing_score(accn)

            validations = self.validation_repo.get_validations_by_accession(accn)
            facts = self.fact_repo.get_selected_facts_by_accession(accn)
            facts_by_metric = {f.metric_id: f for f in facts}

            # Fetch parsed iXBRL facts for original excerpt generation
            from app.database.repositories.xbrl_fact_repository import XBRLFactRepository
            xbrl_facts = XBRLFactRepository().get_facts_by_accession(accn)
            xbrl_by_concept = {xf.concept_name.lower(): xf for xf in xbrl_facts if xf.numeric_value is not None}

            # Check existing reviews
            reviews = self.review_repo.get_reviews_by_accession(accn)
            latest_review_by_metric = {}
            for r in reviews:
                latest_review_by_metric[r.metric_id or "FILING"] = r

            # Check workflow status if exists
            thread_id = f"thread_{accn}"
            wf_state = None
            try:
                wf_state = self.workflow_service.get_workflow_state(thread_id)
            except Exception:
                pass

            # Examine canonical metrics
            all_metric_ids = set(facts_by_metric.keys()) | set(scores_by_metric.keys())

            for m_id in sorted(all_metric_ids):
                fact = facts_by_metric.get(m_id)
                score_rec = scores_by_metric.get(m_id)

                # Determine validation status involving this metric
                relevant_vals = [
                    v for v in validations
                    if m_id in v.input_metrics or any(m_id in k for k in v.input_metrics.keys())
                ]
                val_status = "PASS"
                val_explanation = "Validation criteria satisfied."
                if relevant_vals:
                    failed_vals = [v for v in relevant_vals if v.status == "FAIL"]
                    warn_vals = [v for v in relevant_vals if v.status == "WARNING"]
                    if failed_vals:
                        val_status = "FAIL"
                        val_explanation = failed_vals[0].explanation
                    elif warn_vals:
                        val_status = "WARNING"
                        val_explanation = warn_vals[0].explanation

                # Escalation triggers
                escalation_reasons = []
                if score_rec and score_rec.review_category in ("MANDATORY_REVIEW", "REVIEW_RECOMMENDED"):
                    escalation_reasons.extend(score_rec.negative_factors or [f"Confidence category: {score_rec.review_category}"])
                if val_status in ("FAIL", "WARNING"):
                    escalation_reasons.append(f"Validation alert: {val_explanation}")

                # Determine if item qualifies for review queue
                existing_rev = latest_review_by_metric.get(m_id)
                review_status = existing_rev.decision if existing_rev else "PENDING"

                # If filing-level mandatory review or workflow paused, include all metrics or flagged metrics
                is_flagged = bool(escalation_reasons) or (existing_rev is not None)
                if not is_flagged and filing_score and filing_score.overall_review_category in ("MANDATORY_REVIEW", "REVIEW_RECOMMENDED"):
                    is_flagged = True
                    escalation_reasons.append(f"Filing-level status: {filing_score.overall_review_category}")

                if is_flagged or accession_number:
                    # Construct readable original-source excerpt and specific flagged reason
                    flagged_reason = " | ".join(escalation_reasons) if escalation_reasons else (
                        f"Validation alert: {val_explanation}" if val_status != "PASS" else "Routine verification queue"
                    )

                    source_lines = []
                    if fact:
                        source_lines.append(f"Official SEC Fact: {fact.taxonomy}:{fact.concept}")
                        source_lines.append(f"  • Extracted Value: {fact.raw_value:,.2f} {fact.unit} (Period: {fact.period_start or 'Instant'} to {fact.period_end})")
                        source_lines.append(f"  • Reporting Form: {fact.form or '10-K'} | Fiscal Period: {fact.fiscal_period or 'FY'} {fact.fiscal_year or ''} | Frame: {fact.frame or 'N/A'}")
                        if fact.selection_explanation:
                            source_lines.append(f"  • Context Provenance: {fact.selection_explanation}")

                    concept_key = (fact.concept or "").lower() if fact else ""
                    matched_xf = xbrl_by_concept.get(concept_key)
                    if matched_xf:
                        source_lines.append(f"  • Inline XBRL Fact: {matched_xf.concept_name} (Context: {matched_xf.context_id})")
                        if matched_xf.source_locator:
                            source_lines.append(f"  • Document Locator: {matched_xf.source_locator}")
                        if matched_xf.source_doc_hash:
                            source_lines.append(f"  • Cryptographic SHA-256 Anchor: {matched_xf.source_doc_hash[:20]}...")

                    source_excerpt = "\n".join(source_lines) if source_lines else "No raw primary source disclosure available."

                    queue_items.append(
                        ReviewQueueItemResponse(
                            accession_number=accn,
                            cik=cik,
                            company_name=filing.company_name,
                            ticker=filing.ticker,
                            report_period=filing.report_period,
                            form_type=filing.form_type,
                            metric_id=m_id,
                            canonical_name=fact.canonical_name if fact else (score_rec.canonical_name if score_rec else m_id),
                            extracted_value=fact.raw_value if fact else None,
                            unit=fact.unit if fact else "USD",
                            concept=fact.concept if fact else None,
                            taxonomy=fact.taxonomy if fact else "us-gaap",
                            quality_score=score_rec.confidence_score if score_rec else None,
                            quality_status=score_rec.status if score_rec else None,
                            review_category=score_rec.review_category if score_rec else None,
                            evidence_refs=score_rec.evidence_references if score_rec else {},
                            source_excerpt=source_excerpt,
                            flagged_reason=flagged_reason,
                            validation_status=val_status,
                            validation_explanation=val_explanation,
                            escalation_reasons=escalation_reasons,
                            review_status=review_status,
                            thread_id=thread_id if wf_state else None,
                        )
                    )

        return queue_items

    def get_approval_escalation_summary(self, accession_number: Optional[str] = None) -> Dict[str, Any]:
        """Compute metrics for values automatically approved vs sent to human review."""
        if accession_number:
            filings = [self.filing_repo.get_by_accession(accession_number)]
            filings = [f for f in filings if f is not None]
        else:
            filings = self.filing_repo.get_recent_filings(limit=50)

        total_extracted_facts = 0
        auto_approved_count = 0
        escalated_for_review_count = 0
        decisions_approved = 0
        decisions_corrected = 0
        decisions_rejected = 0
        pending_review_count = 0

        for filing in filings:
            accn = filing.accession_number
            facts = self.fact_repo.get_selected_facts_by_accession(accn)
            scores = {s.metric_id: s for s in self.scoring_repo.get_metric_scores_by_accession(accn)}
            validations = self.validation_repo.get_validations_by_accession(accn)
            val_failed_metrics = set()
            for v in validations:
                if v.status in ("FAIL", "WARNING"):
                    for k in v.input_metrics.keys():
                        val_failed_metrics.add(k)

            reviews = {r.metric_id: r for r in self.review_repo.get_reviews_by_accession(accn)}

            for f in facts:
                total_extracted_facts += 1
                sc = scores.get(f.metric_id)
                has_val_issue = f.metric_id in val_failed_metrics
                is_low_conf = sc and sc.review_category in ("MANDATORY_REVIEW", "REVIEW_RECOMMENDED")

                if not is_low_conf and not has_val_issue:
                    auto_approved_count += 1
                else:
                    escalated_for_review_count += 1
                    rev = reviews.get(f.metric_id)
                    if rev:
                        if rev.decision == "APPROVED":
                            decisions_approved += 1
                        elif rev.decision == "CORRECTED":
                            decisions_corrected += 1
                        elif rev.decision == "REJECTED":
                            decisions_rejected += 1
                    else:
                        pending_review_count += 1

        auto_approved_pct = (auto_approved_count / total_extracted_facts * 100.0) if total_extracted_facts else 0.0
        escalated_pct = (escalated_for_review_count / total_extracted_facts * 100.0) if total_extracted_facts else 0.0

        return {
            "total_extracted_values": total_extracted_facts,
            "auto_approved_count": auto_approved_count,
            "auto_approved_pct": round(auto_approved_pct, 1),
            "escalated_for_review_count": escalated_for_review_count,
            "escalated_pct": round(escalated_pct, 1),
            "decisions_approved": decisions_approved,
            "decisions_corrected": decisions_corrected,
            "decisions_rejected": decisions_rejected,
            "pending_review_count": pending_review_count,
        }

    def get_active_corrections_for_filing(self, accession_number: str) -> Dict[str, float]:
        """Retrieve all active (non-rejected) corrections for a filing, keyed by metric_id.

        When multiple corrections exist for the same metric, the latest one wins
        (reviews are returned ordered by review_round ASC, created_at ASC).
        A REJECTED decision for a metric removes any prior correction for that metric.
        """
        reviews = self.review_repo.get_reviews_by_accession(accession_number)
        active: Dict[str, float] = {}
        for r in reviews:
            if r.decision == "CORRECTED" and r.metric_id and r.corrected_value is not None:
                active[r.metric_id] = r.corrected_value
            elif r.decision == "REJECTED" and r.metric_id:
                active.pop(r.metric_id, None)
        return active

    def submit_review(self, request: SubmitReviewRequest) -> SubmitReviewResponse:
        """Process human reviewer decision (Approve, Correct, Reject).

        Guarantees:
        - Non-empty reviewer identity (never automated/LLM approval)
        - Idempotency key prevents duplicate execution
        - Corrections preserve original value and trigger affected validations rerun
        - Rejections remain explicitly marked as unresolved
        - LangGraph workflow resumes if currently paused
        """
        # 1. Validate Reviewer Identity
        rev_id = (request.reviewer_id or "").strip()
        if not rev_id:
            raise ValueError("Reviewer identity ('reviewer_id') is required.")
        if rev_id.lower() in ("ai", "llm", "system", "bot", "auto"):
            raise ValueError(f"Reviewer identity cannot be automated entity ('{rev_id}'). Human reviewer is required.")

        # 2. Validate Decision
        decision = (request.decision or "").strip().upper()
        if decision not in ("APPROVED", "CORRECTED", "REJECTED"):
            raise ValueError(f"Invalid decision '{decision}'. Must be 'APPROVED', 'CORRECTED', or 'REJECTED'.")

        # 3. Validate Comment
        comment = (request.comment or "").strip()
        if not comment:
            raise ValueError("Mandatory audit comment / justification is required for human review.")

        # 4. Validate Correction Requirements
        if decision == "CORRECTED":
            if request.corrected_value is None:
                raise ValueError("A numeric 'corrected_value' must be provided for a 'CORRECTED' decision.")
            if not isinstance(request.corrected_value, (int, float)) or math.isnan(request.corrected_value) or math.isinf(request.corrected_value):
                raise ValueError(f"Invalid corrected_value '{request.corrected_value}'. Must be a finite number.")

        # 5. Idempotency Check
        idemp_key = request.idempotency_key
        if idemp_key:
            if not validate_idempotency_key(idemp_key):
                raise ValueError(f"Invalid idempotency key format: '{idemp_key}'.")
        else:
            idemp_key = generate_idempotency_key(
                accession_number=request.accession_number,
                metric_id=request.metric_id,
                decision=decision,
                reviewer_id=rev_id,
                corrected_value=request.corrected_value,
            )

        is_dup, existing_record = self.idempotency_mgr.check_idempotency(idemp_key)
        if is_dup and existing_record:
            return SubmitReviewResponse(
                review_id=existing_record.review_id,
                accession_number=existing_record.accession_number,
                thread_id=existing_record.thread_id,
                metric_id=existing_record.metric_id,
                canonical_name=existing_record.canonical_name,
                review_round=existing_record.review_round,
                reviewer_id=existing_record.reviewer_id,
                decision=existing_record.decision,
                original_value=existing_record.original_value,
                corrected_value=existing_record.corrected_value,
                unit=existing_record.unit,
                comment=existing_record.comment,
                evidence_used=existing_record.evidence_used,
                idempotency_key=existing_record.idempotency_key or idemp_key,
                is_duplicate=True,
                previous_validation_status=existing_record.previous_validation_status,
                new_validation_status=existing_record.new_validation_status,
                revalidation_summary=None,
                created_at=existing_record.created_at,
            )

        # 6. Retrieve Original Fact to Preserve Original Value
        original_value = None
        canonical_name = request.metric_id or "Filing"
        unit = request.unit or "USD"

        if request.metric_id:
            facts = self.fact_repo.get_selected_facts_by_accession(request.accession_number)
            matched = [f for f in facts if f.metric_id == request.metric_id]
            if matched:
                original_value = matched[0].raw_value
                canonical_name = matched[0].canonical_name
                unit = request.unit or matched[0].unit

        # 7. Rerun Affected Validations on Correction
        prev_val_status = None
        new_val_status = None
        reval_summary = None

        if decision == "CORRECTED" and request.metric_id:
            summary_before = self.validation_repo.get_validation_summary(request.accession_number)
            prev_val_status = "PASS" if summary_before["failed"] == 0 else "FAIL"

            # Retrieve all previously active corrections for this filing
            active_overrides = self.get_active_corrections_for_filing(request.accession_number)
            # Merge current incoming correction (latest takes precedence)
            active_overrides[request.metric_id] = request.corrected_value

            # Rerun validations with consolidated fact_overrides preserving database facts intact
            revalidated_records = self.validation_engine.validate_filing(
                accession_number=request.accession_number,
                fact_overrides=active_overrides,
                persist=True,
            )
            summary_after = self.validation_repo.get_validation_summary(request.accession_number)
            new_val_status = "PASS" if summary_after["failed"] == 0 else "FAIL"
            reval_summary = summary_after

        elif decision in ("APPROVED", "REJECTED") and request.metric_id:
            # If this metric was previously corrected, an APPROVED or REJECTED decision deactivates that correction
            existing_active = self.get_active_corrections_for_filing(request.accession_number)
            if request.metric_id in existing_active:
                existing_active.pop(request.metric_id, None)
                summary_before = self.validation_repo.get_validation_summary(request.accession_number)
                prev_val_status = "PASS" if summary_before["failed"] == 0 else "FAIL"

                revalidated_records = self.validation_engine.validate_filing(
                    accession_number=request.accession_number,
                    fact_overrides=existing_active if existing_active else None,
                    persist=True,
                )
                summary_after = self.validation_repo.get_validation_summary(request.accession_number)
                new_val_status = "PASS" if summary_after["failed"] == 0 else "FAIL"
                reval_summary = summary_after

        # 8. Resume LangGraph Workflow if Thread is Paused
        thread_id = request.thread_id or f"thread_{request.accession_number}"
        try:
            wf_status = self.workflow_service.get_workflow_state(thread_id)
            if wf_status and wf_status.get("is_paused_for_review"):
                active_corrections = self.get_active_corrections_for_filing(request.accession_number)
                if decision == "CORRECTED" and request.metric_id:
                    active_corrections[request.metric_id] = request.corrected_value
                elif request.metric_id:
                    active_corrections.pop(request.metric_id, None)

                self.workflow_service.resume_workflow(
                    thread_id=thread_id,
                    decision=decision,
                    reviewer_id=rev_id,
                    decision_notes=comment,
                    corrected_values=active_corrections if active_corrections else None,
                )
        except Exception as e:
            logger.warning(f"Workflow resumption for thread {thread_id} skipped or non-blocking: {e}")

        # 9. Persist Human Review Record
        prev_round = self.review_repo.get_latest_review_round(request.accession_number, request.metric_id)
        current_round = prev_round + 1
        review_id = f"rev_{request.accession_number}_{request.metric_id or 'filing'}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        review_rec = ReviewRecord(
            review_id=review_id,
            accession_number=request.accession_number,
            thread_id=thread_id,
            metric_id=request.metric_id,
            canonical_name=canonical_name,
            review_round=current_round,
            reviewer_id=rev_id,
            decision=decision,
            original_value=original_value,
            corrected_value=request.corrected_value if decision == "CORRECTED" else None,
            unit=unit,
            comment=comment,
            evidence_used=request.evidence_used,
            idempotency_key=idemp_key,
            previous_validation_status=prev_val_status,
            new_validation_status=new_val_status,
            metadata_json="{}",
            created_at=_now_iso(),
        )
        saved = self.review_repo.save_review(review_rec)

        # 10. Append to Tamper-Evident Audit Ledger (Mandatory Audit Guarantee)
        try:
            from app.audit.ledger import AuditLedgerService
            audit_service = AuditLedgerService()
            audit_service.record_event(
                event_type="REVIEW_DECISION_RECORDED",
                actor=rev_id,
                payload={
                    "review_id": review_id,
                    "metric_id": request.metric_id,
                    "canonical_name": canonical_name,
                    "decision": decision,
                    "original_value": original_value,
                    "corrected_value": request.corrected_value if decision == "CORRECTED" else None,
                    "unit": unit,
                    "comment": comment,
                    "evidence_used": request.evidence_used,
                    "idempotency_key": idemp_key,
                    "review_round": current_round,
                    "previous_validation_status": prev_val_status,
                    "new_validation_status": new_val_status,
                },
                accession_number=request.accession_number,
                workflow_id=thread_id,
                metric_id=request.metric_id,
            )
        except Exception as ae:
            # Audit guarantee: a review decision CANNOT be recorded without its audit event
            logger.error(f"Audit ledger logging failed: {ae}. Rolling back review record {review_id} to preserve audit guarantees.")
            try:
                self.review_repo.delete_review(review_id)
            except Exception as de:
                logger.error(f"Failed to delete un-audited review record: {de}")
            raise RuntimeError(f"Audit guarantee failure: review decision cannot be recorded without its audit event: {ae}") from ae

        return SubmitReviewResponse(
            review_id=saved.review_id,
            accession_number=saved.accession_number,
            thread_id=saved.thread_id,
            metric_id=saved.metric_id,
            canonical_name=saved.canonical_name,
            review_round=saved.review_round,
            reviewer_id=saved.reviewer_id,
            decision=saved.decision,
            original_value=saved.original_value,
            corrected_value=saved.corrected_value,
            unit=saved.unit,
            comment=saved.comment,
            evidence_used=saved.evidence_used,
            idempotency_key=idemp_key,
            is_duplicate=False,
            previous_validation_status=saved.previous_validation_status,
            new_validation_status=saved.new_validation_status,
            revalidation_summary=reval_summary,
            created_at=saved.created_at,
        )
