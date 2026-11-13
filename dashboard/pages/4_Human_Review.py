import sys
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.api.schemas.review import SubmitReviewRequest
from app.database.connection import check_db_health
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.review_repository import ReviewRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.review.service import ReviewService
from app.workflow.resume import WorkflowService
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    format_currency,
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

st.set_page_config(
    page_title="FilingGuard AI - Human Review & Auditor Interface",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_sidebar_branding()

render_header(
    title="Human Auditor Review & Decision Interface",
    subtitle="Evidence-linked auditor review loop. Review flagged metrics, inspect citations, submit idempotent approvals/corrections, and resume LangGraph workflows.",
    category_chip="PIPELINE STAGES 5 & 6 • HUMAN OVERSIGHT",
)

if not check_db_health():
    st.error("Database connection is offline. Please check SQLite database configuration.")
    st.stop()

filing_repo = FilingRepository()
scoring_repo = ScoringRepository()
val_repo = ValidationRepository()
review_repo = ReviewRepository()
review_service = ReviewService()
workflow_service = WorkflowService()

# Select target filing
all_filings = filing_repo.get_recent_filings(limit=50)

if not all_filings:
    st.info("No filings found in the database. Please download or ingest an SEC filing first.")
    st.stop()

filing_options = {
    f"{f.company_name or 'Unknown'} ({f.ticker or 'N/A'}) - Form 10-K [{f.report_period or f.filing_date}] — Accn: {f.accession_number}": f.accession_number
    for f in all_filings
}

selected_label = st.selectbox("Select Target Filing to Review:", options=list(filing_options.keys()))
selected_accn = filing_options[selected_label]
selected_filing = filing_repo.get_by_accession(selected_accn)

# Default thread ID
thread_id = f"thread_{selected_accn}"

# Top Action Toolbar
col_act1, col_act2 = st.columns([3, 4])
with col_act1:
    if st.button("🚀 Run Workflow to Review Gate", type="primary", use_container_width=True):
        with st.spinner("Executing LangGraph agentic pipeline..."):
            t_id, state = workflow_service.start_workflow(
                accession_number=selected_accn,
                cik=selected_filing.cik if selected_filing else None,
                thread_id=thread_id,
            )
            st.success(f"Workflow reached: {state.get('workflow_status')} on thread `{t_id}`.")
            st.rerun()

# Retrieve current workflow state from durable SQLite checkpointer
status_data = workflow_service.get_workflow_state(thread_id)
values = status_data["values"] if status_data else {}
is_paused = status_data.get("is_paused_for_review", False) if status_data else False
wf_status = values.get("workflow_status", "NOT_STARTED")
current_stage = values.get("current_stage", "none")

# ---------------------------------------------------------------------------
# Section 1: Workflow Status KPI Cards
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    wf_status_type = "success" if wf_status == "COMPLETED" else ("warning" if wf_status == "PAUSED_FOR_REVIEW" else ("danger" if wf_status in ("FAILED", "REJECTED") else "info"))
    status_icon = "🟢" if wf_status == "COMPLETED" else ("🟡" if wf_status == "PAUSED_FOR_REVIEW" else "⚪")
    render_kpi_card(
        label="Workflow Status",
        value=f"{status_icon} {wf_status.replace('_', ' ')}",
        subtext=f"Thread: {thread_id[:16]}...",
        status=wf_status_type,
    )

with kpi2:
    render_kpi_card(
        label="Current Stage",
        value=current_stage.upper(),
        subtext="LangGraph State Machine",
        status="info",
    )

with kpi3:
    gate_status = "warning" if is_paused else "success"
    gate_label = "🚨 PAUSED (Action Required)" if is_paused else "✅ CLEARED"
    render_kpi_card(
        label="Review Gate",
        value=gate_label,
        subtext="Interrupt Checkpoint State",
        status=gate_status,
    )

with kpi4:
    scores = values.get("quality_scores") or {}
    ov_score = scores.get("overall_score")
    render_kpi_card(
        label="Filing Confidence",
        value=f"{ov_score:.2f} / 1.00" if ov_score is not None else "Pending",
        subtext=scores.get("overall_review_category", "Unscored").replace("_", " "),
        status="success" if (ov_score or 0) >= 0.8 else "warning",
    )

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2: Auditor Interface Tabs
# ---------------------------------------------------------------------------
st.divider()

tab_queue, tab_gate, tab_history = st.tabs([
    "📋 Review Queue & Fact Inspection",
    "🚨 Workflow Gate & Resumption",
    "📜 Historical Review Decisions",
])

# ---------------------------------------------------------------------------
# TAB 1: REVIEW QUEUE & ACTION FORM
# ---------------------------------------------------------------------------
with tab_queue:
    st.subheader("Items Flagged for Auditor Review")
    st.caption("Metrics requiring human auditor sign-off due to low confidence scores, validation anomalies, or missing data.")

    # Approval and Escalation Counts (Gap 7)
    escalation_stats = review_service.get_approval_escalation_summary(selected_accn)
    esc_col1, esc_col2, esc_col3, esc_col4 = st.columns(4)
    with esc_col1:
        render_kpi_card(
            label="Total Extracted Metrics",
            value=str(escalation_stats["total_extracted_values"]),
            subtext="Filing facts assessed",
            status="info",
        )
    with esc_col2:
        render_kpi_card(
            label="Auto-Approved Metrics",
            value=f"{escalation_stats['auto_approved_count']} ({escalation_stats['auto_approved_pct']}%)",
            subtext="Score ≥ 0.85 & Validations PASS",
            status="success",
        )
    with esc_col3:
        render_kpi_card(
            label="Sent to Human Review",
            value=f"{escalation_stats['escalated_for_review_count']} ({escalation_stats['escalated_pct']}%)",
            subtext=f"{escalation_stats['pending_review_count']} pending decisions",
            status="warning" if escalation_stats['escalated_for_review_count'] > 0 else "neutral",
        )
    with esc_col4:
        total_decided = escalation_stats["decisions_approved"] + escalation_stats["decisions_corrected"] + escalation_stats["decisions_rejected"]
        render_kpi_card(
            label="Decisions Logged",
            value=str(total_decided),
            subtext=f"{escalation_stats['decisions_approved']} apprv, {escalation_stats['decisions_corrected']} corr, {escalation_stats['decisions_rejected']} rej",
            status="neutral",
        )

    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    queue_items = review_service.get_review_queue(selected_accn)

    if not queue_items:
        st.info("No escalated items pending review for this filing. All facts have passed deterministic gates.")
    else:
        filing_validations = val_repo.get_validations_by_accession(selected_accn)
        summary_rows = []
        for item in queue_items:
            summary_rows.append({
                "Metric": item.canonical_name,
                "Extracted Value": format_currency(item.extracted_value),
                "Unit": item.unit,
                "Quality Score": f"{item.quality_score:.2f}" if item.quality_score else "N/A",
                "Category": item.review_category or "AUTO_PASS",
                "Validation Status": item.validation_status or "N/A",
                "Review State": item.review_status,
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
        st.subheader("Item Drilldown & Review Action")

        selected_metric_idx = st.selectbox(
            "Select Metric to Inspect & Review:",
            range(len(queue_items)),
            format_func=lambda i: f"{queue_items[i].canonical_name} — Status: {queue_items[i].review_status}",
        )
        target_item = queue_items[selected_metric_idx]

        col_left, col_right = st.columns([1, 1])

        with col_left:
            related_validations = [
                validation
                for validation in filing_validations
                if target_item.metric_id in validation.input_metrics
                or any(target_item.metric_id in key for key in validation.input_metrics)
            ]
            suggested_actions = [
                validation.recommendation
                for validation in related_validations
                if validation.recommendation
            ]
            st.markdown(
                f"""
                <div style="background-color: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 0.85rem; margin-bottom: 0.75rem;">
                    <div style="font-weight: 700; color: #9a3412; font-size: 0.9rem;">🚩 WHY THIS VALUE WAS FLAGGED FOR REVIEW:</div>
                    <div style="font-size: 0.86rem; color: #7c2d12; margin-top: 0.25rem; line-height: 1.5;">
                        {target_item.flagged_reason or 'Confidence score or validation check did not meet auto-pass threshold.'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class="fg-card">
                    <div style="font-weight: 700; font-size: 1.05rem; color: #101b32; margin-bottom: 0.5rem;">
                        Fact Evidence: {target_item.canonical_name}
                    </div>
                    <div style="font-size: 0.9rem; color: #334155; line-height: 1.6;">
                        • <b>Metric ID</b>: <code>{target_item.metric_id}</code><br>
                        • <b>Reported Value</b>: <b>{format_currency(target_item.extracted_value)}</b> ({target_item.unit})<br>
                        • <b>Taxonomy Concept</b>: <code>{target_item.concept}</code><br>
                        • <b>Quality Score</b>: <b>{target_item.quality_score:.2f}</b> ({target_item.quality_status})<br>
                        • <b>Review Routing</b>: <code>{target_item.review_category}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if target_item.source_excerpt:
                st.markdown("**Original Source Excerpt & Provenance:**")
                st.code(target_item.source_excerpt, language="text")

            st.markdown("**Suggested correction / follow-up**")
            if suggested_actions:
                for suggestion in dict.fromkeys(suggested_actions):
                    st.info(suggestion)
            else:
                st.caption("No system-generated correction is available. Base any correction on independently reviewed filing evidence.")

            if target_item.escalation_reasons:
                st.markdown("**Escalation Triggers / Reduction Reasons:**")
                for r in target_item.escalation_reasons:
                    st.warning(f"⚠️ {r}")

            if target_item.evidence_refs:
                with st.expander("🔍 View Primary Document Evidence Citations"):
                    st.json(target_item.evidence_refs)

        with col_right:
            st.markdown("**Submit Auditor Review Action**")
            with st.form(f"review_form_{target_item.metric_id}"):
                decision = st.selectbox("Auditor Decision:", ["APPROVED", "CORRECTED", "REJECTED"], key=f"dec_{target_item.metric_id}")
                reviewer_id = st.text_input("Reviewer Identity:", value="auditor_lead_1", key=f"rev_{target_item.metric_id}")

                corrected_val = None
                evidence_used = ""
                if decision == "CORRECTED":
                    corrected_val = st.number_input(
                        "Corrected Value (USD):",
                        value=float(target_item.extracted_value or 0.0),
                        format="%.2f",
                        key=f"corr_{target_item.metric_id}",
                    )
                    evidence_used = st.text_input(
                        "Evidence Citation for Correction:",
                        value="10-K Consolidated Balance Sheets, Note 12",
                        key=f"ev_{target_item.metric_id}",
                    )

                comment = st.text_area(
                    "Mandatory Auditor Comment:",
                    placeholder="Document audit rationale, evidence inspected, and reconciliation note...",
                    key=f"comm_{target_item.metric_id}",
                )

                idemp_input = st.text_input(
                    "Idempotency Key (Optional, auto-generated if blank):",
                    value="",
                    key=f"idemp_{target_item.metric_id}",
                )

                submit_btn = st.form_submit_button("Submit Review Decision", type="primary", use_container_width=True)

                if submit_btn:
                    if not comment.strip():
                        st.error("Audit comment is mandatory for all review decisions.")
                    elif not reviewer_id.strip():
                        st.error("Reviewer identity is required.")
                    else:
                        try:
                            req = SubmitReviewRequest(
                                accession_number=selected_accn,
                                metric_id=target_item.metric_id,
                                decision=decision,
                                reviewer_id=reviewer_id.strip(),
                                corrected_value=corrected_val,
                                comment=comment.strip(),
                                evidence_used=evidence_used.strip() or None,
                                idempotency_key=idemp_input.strip() or None,
                                thread_id=thread_id,
                            )
                            res = review_service.submit_review(req)
                            st.success(f"Review `{res.decision}` recorded! Review ID: `{res.review_id}`")
                            reval_sum = getattr(res, "revalidation_summary", None)
                            if reval_sum:
                                p = reval_sum.get("passed", 0)
                                f = reval_sum.get("failed", 0)
                                w = reval_sum.get("warnings", 0)
                                st.info(f"Revalidation triggered: {p} passed, {f} failed, {w} warnings.")
                            elif getattr(res, "new_validation_status", None):
                                st.info(f"Validation status updated to: {res.new_validation_status}")
                            else:
                                st.info("Review decision recorded successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Review submission failed: {str(e)}")

# ---------------------------------------------------------------------------
# TAB 2: WORKFLOW GATE & RESUMPTION
# ---------------------------------------------------------------------------
with tab_gate:
    st.subheader("LangGraph Interrupt State & Workflow Resumption")
    st.caption("Inspect paused workflow checkpoints and resume execution using LangGraph Command(resume=decision).")

    if not status_data:
        st.info("No active workflow thread found for this filing. Click 'Run Workflow to Review Gate' above to launch.")
    else:
        c_state1, c_state2 = st.columns(2)
        with c_state1:
            st.markdown(f"**Thread ID**: `{thread_id}`")
            st.markdown(f"**Workflow Status**: `{wf_status}`")
            st.markdown(f"**Paused for Review**: `{'Yes - at interrupt()' if is_paused else 'No'}`")
            st.markdown(f"**Next Steps in Graph**: `{status_data.get('next_steps')}`")

        with c_state2:
            if is_paused:
                st.warning("⚠️ Workflow is waiting at the Human Review Gate.")
                st.markdown("Auditors can resume the workflow using a global decision:")
                c_res1, c_res2 = st.columns(2)
                with c_res1:
                    if st.button("🟢 Approve & Complete Workflow", type="primary", use_container_width=True):
                        with st.spinner("Resuming LangGraph state machine..."):
                            resumed_state = workflow_service.resume_workflow(
                                thread_id=thread_id,
                                decision="APPROVED",
                                reviewer_id="auditor_lead",
                                decision_notes="Global audit approval granted.",
                            )
                            st.success(f"Workflow resumed! Final status: `{resumed_state.get('workflow_status')}`")
                            st.rerun()
                with c_res2:
                    if st.button("🔴 Reject & Terminate Workflow", use_container_width=True):
                        with st.spinner("Terminating workflow with rejection..."):
                            resumed_state = workflow_service.resume_workflow(
                                thread_id=thread_id,
                                decision="REJECTED",
                                reviewer_id="auditor_lead",
                                decision_notes="Filing rejected due to audit non-conformance.",
                            )
                            st.error(f"Workflow terminated with status: `{resumed_state.get('workflow_status')}`")
                            st.rerun()
            else:
                st.success("✅ Workflow is not currently blocked at an interrupt gate.")

        # Stage Execution Log
        with st.expander("📜 View Checkpointed Execution Trace", expanded=True):
            for entry in values.get("execution_log", []):
                st.text(entry)

# ---------------------------------------------------------------------------
# TAB 3: REVIEW DECISIONS HISTORY
# ---------------------------------------------------------------------------
with tab_history:
    st.subheader("Historical Auditor Review Decisions")
    st.caption("Audited decision trail recording reviewer identity, original vs. corrected figures, and rationale.")

    history_records = review_repo.get_reviews_by_accession(selected_accn)

    if not history_records:
        st.info("No human review records logged yet for this filing.")
    else:
        history_rows = []
        for r in history_records:
            history_rows.append({
                "Review ID": r.review_id,
                "Round": r.review_round,
                "Metric": r.canonical_name or r.metric_id or "FILING",
                "Decision": r.decision,
                "Original Value": format_currency(r.original_value),
                "Corrected Value": format_currency(r.corrected_value) if r.corrected_value is not None else "—",
                "Reviewer ID": r.reviewer_id,
                "Audit Comment": r.comment,
                "Validation Before": r.previous_validation_status or "—",
                "Validation After": r.new_validation_status or "Not recorded",
                "Timestamp (UTC)": r.created_at,
                "Idempotency Key": r.idempotency_key or "N/A",
            })
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "⚠️ **Audit Disclaimer**: LangGraph orchestrates workflow execution and checkpointing. "
    "All financial extraction, confidence scoring, and accounting checks are executed deterministically. "
    "Auditor approvals and corrections are cryptographically and statefully recorded in SQLite."
)
