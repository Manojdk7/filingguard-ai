import sys
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.database.connection import check_db_health
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.reconciliation_repository import ReconciliationRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.scoring.quality_score import ConfidenceScoringEngine
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    format_currency,
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

st.set_page_config(
    page_title="FilingGuard AI - Extraction & Confidence Scoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_sidebar_branding()

render_header(
    title="Extraction Results & Confidence Scoring",
    subtitle="Deterministic fact extraction, cross-source reconciliation against Inline XBRL, and 5-factor confidence scoring.",
    category_chip="PIPELINE STAGES 2 & 3 • EXTRACTION & SCORING",
)

if not check_db_health():
    st.error("Database connection is offline. Please check SQLite database configuration.")
    st.stop()

filing_repo = FilingRepository()
scoring_repo = ScoringRepository()
fact_repo = FactRepository()
recon_repo = ReconciliationRepository()
scoring_engine = ConfidenceScoringEngine()

# Filing selector
all_filings = filing_repo.get_recent_filings(limit=50)

if not all_filings:
    st.info("No filings found in the database. Please download or ingest an SEC filing first.")
    st.stop()

filing_options = {
    f"{f.company_name or 'Unknown'} ({f.ticker or 'N/A'}) - Form 10-K [{f.report_period or f.filing_date}] — Accn: {f.accession_number}": f.accession_number
    for f in all_filings
}

selected_label = st.selectbox("Select Target Filing to Inspect:", options=list(filing_options.keys()))
selected_accn = filing_options[selected_label]
selected_filing = filing_repo.get_by_accession(selected_accn)

# Action button
col_btn, col_empty = st.columns([2, 5])
with col_btn:
    if st.button("⚡ Score / Re-Score Filing", type="primary", use_container_width=True):
        with st.spinner("Executing deterministic scoring engine..."):
            filing_score, metric_scores = scoring_engine.score_filing(selected_accn)
            st.success("Filing successfully scored and results persisted.")
            st.rerun()

# Fetch existing scoring results
filing_score = scoring_repo.get_filing_score(selected_accn)
metric_scores = scoring_repo.get_metric_scores_by_accession(selected_accn)

if not filing_score:
    st.warning("This filing has not been scored yet. Click 'Score / Re-Score Filing' above to calculate confidence.")
    st.stop()

# ---------------------------------------------------------------------------
# Section 1: Header KPI Metric Cards
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    kpi_status = "success" if filing_score.overall_status == "HIGH" else ("warning" if filing_score.overall_status == "MEDIUM" else "danger")
    render_kpi_card(
        label="Overall Quality Score",
        value=f"{filing_score.quality_score_100:.1f}%",
        subtext=f"Score: {filing_score.overall_score:.2f} / 1.00",
        status=kpi_status,
    )

with kpi2:
    status_icon = "🟢" if filing_score.overall_status == "HIGH" else ("🟡" if filing_score.overall_status == "MEDIUM" else "🔴")
    render_kpi_card(
        label="Confidence Tier",
        value=f"{status_icon} {filing_score.overall_status}",
        subtext="Evidence & Mapping Validated",
        status=kpi_status,
    )

with kpi3:
    cat_text = filing_score.overall_review_category.replace("_", " ")
    cat_status = "success" if filing_score.overall_review_category == "AUTO_PASS" else ("warning" if filing_score.overall_review_category == "REVIEW_RECOMMENDED" else "danger")
    render_kpi_card(
        label="Routing Decision",
        value=cat_text,
        subtext="Audit Gate Recommendation",
        status=cat_status,
    )

with kpi4:
    cov_status = "success" if filing_score.metrics_missing_count == 0 else "warning"
    render_kpi_card(
        label="Metric Coverage",
        value=f"{filing_score.metrics_assessed_count} Assessed",
        subtext="All 10 Canonical Present" if filing_score.metrics_missing_count == 0 else f"{filing_score.metrics_missing_count} Metric(s) Missing",
        status=cov_status,
    )

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2: Document Integrity & Summary Banner
# ---------------------------------------------------------------------------
integrity = scoring_engine.verify_document_integrity(selected_accn)
if integrity.exists and integrity.hash_matched:
    st.markdown(
        f"""
        <div style="background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 0.85rem 1.25rem; margin-bottom: 1rem;">
            <div style="font-weight: 700; color: #065f46; font-size: 0.9rem;">
                🔒 DOCUMENT INTEGRITY VERIFIED (SHA-256 MATCH)
            </div>
            <div style="color: #065f46; font-size: 0.85rem; margin-top: 0.15rem;">
                Primary filing <code>{selected_filing.primary_document}</code> matches recorded archive hash (<code>{integrity.stored_hash[:16]}...</code>).
                <i>{integrity.notes}</i>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif integrity.exists and not integrity.hash_matched:
    st.error(
        f"🚨 **Integrity Alert**: Local document hash does NOT match the stored archive hash! "
        f"Stored: `{integrity.stored_hash}`, Calculated: `{integrity.calculated_hash}`."
    )

# Summary explanation card
with st.expander("📋 Filing Evaluation Summary & Score Reductions", expanded=bool(filing_score.reduction_reasons)):
    st.markdown(f"**Evaluation Summary**: {filing_score.summary_explanation}")
    if filing_score.reduction_reasons:
        st.markdown("**Reasons for Score Reductions / Review Triggers:**")
        for reason in filing_score.reduction_reasons:
            st.markdown(f"- ⚠️ {reason}")

# ---------------------------------------------------------------------------
# Section 3: Canonical Financial Metrics (Clean Tabbed Tables)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Canonical Financial Metrics & Quality Scores")

facts = fact_repo.get_selected_facts_by_accession(selected_accn)
facts_map = {f.metric_id: f for f in facts}
recons = recon_repo.get_reconciliations_by_accession(selected_accn)
recons_map = {r.metric_id: r for r in recons}

tab_summary, tab_factors = st.tabs(["📊 Financial Metrics Summary", "⚖️ 5-Factor Scoring Breakdown"])

with tab_summary:
    summary_rows = []
    for m in metric_scores:
        f = facts_map.get(m.metric_id)
        r = recons_map.get(m.metric_id)

        val_display = format_currency(f.raw_value) if f else ("N/A" if not r or r.ixbrl_value is None else format_currency(r.ixbrl_value))
        recon_status = r.status.replace("_", " ") if r else ("missing in both" if not f else "single source")

        summary_rows.append({
            "Canonical Metric": m.canonical_name,
            "Reported Value": val_display,
            "Quality Score": f"{m.confidence_score * 100:.1f}% ({m.confidence_score:.2f})",
            "Confidence Tier": m.status,
            "Audit Routing": m.review_category.replace("_", " "),
            "Cross-Reconciliation": recon_status,
        })

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

with tab_factors:
    factor_rows = []
    factor_labels = {
        "source_reliability": "Source reliability",
        "cross_source_agreement": "Cross-source agreement",
        "period_compatibility": "Period compatibility",
        "unit_dimensional_compatibility": "Unit / dimensional compatibility",
        "extraction_mapping_quality": "Extraction / mapping quality",
        "evidence_quality": "Legacy: evidence quality",
        "concept_mapping_quality": "Legacy: concept mapping",
        "period_context_quality": "Legacy: period context",
        "unit_quality": "Legacy: unit quality",
        "cross_check_quality": "Legacy: cross-check",
    }
    for m in metric_scores:
        details = m.evidence_references.get("factor_breakdown", {})
        for factor_name, raw_score in m.factors.items():
            detail = details.get(factor_name, {})
            factor_rows.append({
                "Metric": m.canonical_name,
                "Factor": factor_labels.get(factor_name, factor_name.replace("_", " ").title()),
                "Raw Score": f"{detail.get('raw_score', raw_score):.2f}",
                "Weight": f"{detail['weight']:.0%}" if "weight" in detail else "Legacy",
                "Weighted Contribution": (
                    f"{detail['weighted_contribution']:.3f}"
                    if "weighted_contribution" in detail else "Not recorded"
                ),
                "Evidence": "; ".join(detail.get("evidence", [])) or "Not recorded for this scoring version",
                "Deduction Reasons": "; ".join(detail.get("deduction_reasons", [])) or "None recorded",
            })
    if any(not m.evidence_references.get("factor_breakdown") for m in metric_scores):
        st.info("Some stored scores use the legacy rubric. Re-score the filing to view weighted contributions and factor-level evidence.")
    st.dataframe(pd.DataFrame(factor_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section 4: Granular Evidence & Factor Explanations
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Granular Factor Evidence & Citations")

for m in metric_scores:
    cat_emoji = "🟢" if m.review_category == "AUTO_PASS" else ("🟡" if m.review_category == "REVIEW_RECOMMENDED" else "🔴")
    header_text = f"{cat_emoji} {m.canonical_name} — Score: {m.confidence_score:.2f} ({m.status}) — {m.review_category.replace('_', ' ')}"

    with st.expander(header_text, expanded=False):
        st.markdown(f"**Auditor Explanation**: {m.explanation}")

        col_pos, col_neg = st.columns(2)
        with col_pos:
            st.markdown("##### 🟢 Positive Contributing Factors")
            if m.positive_factors:
                for p in m.positive_factors:
                    st.markdown(f"- {p}")
            else:
                st.caption("No positive factors identified.")

        with col_neg:
            st.markdown("##### 🔴 Warnings & Reduction Drivers")
            if m.negative_factors:
                for n in m.negative_factors:
                    st.markdown(f"- {n}")
            else:
                st.caption("No negative factors detected.")

        if m.review_recommendations:
            st.markdown("##### 💡 Review Recommendations")
            for rec in m.review_recommendations:
                st.info(rec)

        st.markdown("##### 🔍 Source Evidence References & Hash Citations")
        st.json(m.evidence_references)

st.divider()
st.caption(
    "⚠️ **Important Disclaimer**: Confidence scores represent extraction evidence quality, source consistency, "
    "and taxonomy validity. A high score does not guarantee underlying corporate accounting truth, and a low score "
    "does not assert fraud. Scores should be used strictly to prioritize human auditor review."
)
