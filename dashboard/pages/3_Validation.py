import sys
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.database.connection import check_db_health
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.validation.engine import FinancialValidationEngine
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    format_currency,
    format_percentage,
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

st.set_page_config(
    page_title="FilingGuard AI - Financial Validation Engine",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_sidebar_branding()

render_header(
    title="Financial Statement Validation Engine",
    subtitle="Deterministic accounting equation verification, operating presentation checks, YoY variance analysis, and cross-statement consistency.",
    category_chip="PIPELINE STAGE 4 • FINANCIAL VALIDATION",
)

if not check_db_health():
    st.error("Database connection is offline. Please check SQLite database configuration.")
    st.stop()

filing_repo = FilingRepository()
val_repo = ValidationRepository()
val_engine = FinancialValidationEngine()

# Filing selector
all_filings = filing_repo.get_recent_filings(limit=50)

if not all_filings:
    st.info("No filings found in the database. Please download or ingest an SEC filing first.")
    st.stop()

filing_options = {
    f"{f.company_name or 'Unknown'} ({f.ticker or 'N/A'}) - Form 10-K [{f.report_period or f.filing_date}] — Accn: {f.accession_number}": f.accession_number
    for f in all_filings
}

selected_label = st.selectbox("Select Target Filing:", options=list(filing_options.keys()))
selected_accn = filing_options[selected_label]
selected_filing = filing_repo.get_by_accession(selected_accn)

# Execution button
col_act, col_info = st.columns([2, 5])
with col_act:
    if st.button("⚡ Execute Financial Validations", type="primary", use_container_width=True):
        with st.spinner("Executing 14 deterministic accounting rules..."):
            results = val_engine.validate_filing(selected_accn)
            st.success(f"Executed {len(results)} validation rules and persisted results.")
            st.rerun()

# Fetch existing validation results
validations = val_repo.get_validations_by_accession(selected_accn)
summary = val_repo.get_validation_summary(selected_accn)

if not validations:
    st.warning("No validation results found for this filing. Click 'Execute Financial Validations' above to run the engine.")
    st.stop()

# ---------------------------------------------------------------------------
# Section 1: Summary KPI Cards
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

overall_status = (
    "FAILED"
    if summary["failed"]
    else (
        "INCOMPLETE"
        if summary["not_evaluated"]
        else ("REVIEW" if summary["warnings"] else "PASSED")
    )
)
overall_status_type = (
    "danger"
    if overall_status == "FAILED"
    else ("warning" if overall_status in ("INCOMPLETE", "REVIEW") else "success")
)

with kpi1:
    render_kpi_card(
        label="Overall Status",
        value=overall_status,
        subtext=f"{summary['total_rules']} recorded rules",
        status=overall_status_type,
    )

with kpi2:
    render_kpi_card(
        label="Passed",
        value=str(summary["passed"]),
        subtext=(
            f"{(summary['passed'] / summary['total_rules'] * 100):.0f}% of recorded rules"
            if summary["total_rules"]
            else "No rules recorded"
        ),
        status="success",
    )

with kpi3:
    render_kpi_card(
        label="Failed",
        value=str(summary["failed"]),
        subtext="Requires auditor inspection" if summary["failed"] else "No failed rules",
        status="danger" if summary["failed"] else "neutral",
    )

with kpi4:
    render_kpi_card(
        label="Warnings",
        value=str(summary["warnings"]),
        subtext="Review threshold variance" if summary["warnings"] else "No warning rules",
        status="warning" if summary["warnings"] else "success",
    )

with kpi5:
    render_kpi_card(
        label="Not Evaluated",
        value=str(summary["not_evaluated"]),
        subtext="Inputs unavailable or inapplicable",
        status="info" if summary["not_evaluated"] else "success",
    )

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

st.subheader("Complete rule register")
st.caption("All recorded rules remain visible here, including failures, warnings, and rules that could not be evaluated.")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Rule": item.rule_name,
                "Category": item.validation_category.replace("_", " "),
                "Status": item.status,
                "Finding": item.failure_reason or item.explanation,
                "Recommendation": item.recommendation or "—",
            }
            for item in validations
        ]
    ),
    use_container_width=True,
    hide_index=True,
)

# ---------------------------------------------------------------------------
# Section 2: Core Balance Sheet & Presentation Checks
# ---------------------------------------------------------------------------
st.divider()
st.subheader("1. Core Accounting & Presentation Checks")
st.caption("Verifies fundamental GAAP arithmetic relationships across reported primary statement line items.")

core_validations = [v for v in validations if v.validation_category in ("balance_sheet", "income_statement")]

for v in core_validations:
    status_icon = "🟢" if v.status == "PASS" else ("🔴" if v.status == "FAIL" else ("🟡" if v.status == "WARNING" else "⚪"))
    badge_label = f"{status_icon} {v.status} — {v.rule_name}"

    with st.expander(badge_label, expanded=(v.status != "PASS")):
        st.markdown(f"**Explanation**: {v.explanation}")

        if v.status == "FAIL":
            st.error(f"**Failure Reason**: {v.failure_reason}\n\n**Recommendation**: {v.recommendation}")
        elif v.status == "WARNING":
            st.warning(f"**Warning**: {v.failure_reason}\n\n**Recommendation**: {v.recommendation}")
        elif v.status == "NOT_EVALUATED":
            st.info(f"**Status Notice**: {v.failure_reason}")

        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.metric("Expected Value", format_currency(v.expected_value))
        with col_c2:
            st.metric("Actual Value", format_currency(v.actual_value))
        with col_c3:
            diff_display = format_currency(v.absolute_difference)
            st.metric("Absolute Difference", diff_display, delta="Balanced" if (v.absolute_difference or 0) == 0 else "Variance")

        # Clean breakdown of input components
        st.markdown("**Reported Statement Inputs:**")
        inputs_list = []
        for k, val in v.input_metrics.items():
            if isinstance(val, (int, float)):
                inputs_list.append(f"- **{k.replace('_', ' ').title()}**: `{format_currency(val)}`")
            else:
                inputs_list.append(f"- **{k.replace('_', ' ').title()}**: `{val}`")
        st.markdown("\n".join(inputs_list))
        if v.evidence_references:
            st.markdown("**Evidence references:**")
            st.json(v.evidence_references)

# ---------------------------------------------------------------------------
# Section 3: Year-over-Year (YoY) Variance Analysis Table
# ---------------------------------------------------------------------------
st.divider()
st.subheader("2. Year-over-Year (YoY) Variance Analysis")
st.caption("Flags material multi-year disclosure changes exceeding established accounting materiality thresholds.")

yoy_validations = [v for v in validations if v.validation_category == "variance"]

if yoy_validations:
    yoy_rows = []
    for v in yoy_validations:
        m_info = v.input_metrics
        c_val = m_info.get("current_value")
        p_val = m_info.get("prior_value")
        pct_diff = (v.relative_difference * 100.0) if v.relative_difference is not None else None

        status_text = "🟢 Normal" if v.status == "PASS" else ("🟡 Variance Warning" if v.status == "WARNING" else "⚪ Undefined")

        yoy_rows.append({
            "Financial Metric": m_info.get("canonical_name", v.rule_name),
            "Status": status_text,
            "YoY Change (%)": f"{pct_diff:+.2f}%" if pct_diff is not None else "N/A",
            "Current FY Value": format_currency(c_val),
            "Prior FY Value": format_currency(p_val),
            "Absolute Change": format_currency(v.absolute_difference),
            "Materiality Threshold": f"±{v.configured_tolerance:.0f}%",
            "Auditor Assessment": v.explanation,
        })

    df_yoy = pd.DataFrame(yoy_rows)
    st.dataframe(df_yoy, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section 4: Cross-Statement Consistency Checks
# ---------------------------------------------------------------------------
st.divider()
st.subheader("3. Cross-Statement Consistency Checks")
st.caption("Verifies cross-schedule alignment (e.g. Net Income and Cash reconciliations between Balance Sheet, Income Statement, and Cash Flows).")

cs_validations = [v for v in validations if v.validation_category == "cross_statement"]

for v in cs_validations:
    status_icon = "🟢" if v.status == "PASS" else ("🔴" if v.status == "FAIL" else "⚪")
    with st.expander(f"{status_icon} {v.status} — {v.rule_name}", expanded=v.status != "PASS"):
        st.markdown(f"**Explanation**: {v.explanation}")
        if v.failure_reason:
            st.warning(f"**Notice**: {v.failure_reason}\n\n**Recommendation**: {v.recommendation}")
        if v.evidence_references:
            st.markdown("**Evidence references:**")
            st.json(v.evidence_references)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Expected Value", format_currency(v.expected_value))
        with c2:
            st.metric("Actual Value", format_currency(v.actual_value))
        with c3:
            st.metric("Discrepancy", format_currency(v.absolute_difference))

st.divider()
st.caption(
    "⚠️ **Audit Disclaimer**: Validation rules check internal arithmetic, presentation structure, and historical variance. "
    "A failed validation or variance warning indicates a disclosure divergence requiring human auditor inspection; "
    "it does not constitute proof of fraud or financial misstatement."
)
