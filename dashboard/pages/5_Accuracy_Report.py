import sys
from html import escape
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.reference_loader import load_reference_dataset
from app.database.connection import check_db_health
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    format_currency,
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

st.set_page_config(
    page_title="FilingGuard AI - Accuracy & Benchmark Report",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_sidebar_branding()

render_header(
    title="Benchmark Evaluation & Accuracy Report",
    subtitle="Compare local extraction results with the configured reference sample; reviewer flags and source provenance are disclosed separately.",
    category_chip="PIPELINE STAGE 7 • BENCHMARK & VERIFICATION",
)

if not check_db_health():
    st.error("Database connection is offline. Please check SQLite database configuration.")
    st.stop()

evaluator = BenchmarkEvaluator()
reference_records = load_reference_dataset()

col_btn, col_info = st.columns([2, 5])
with col_btn:
    run_fresh = st.button("🚀 Run Benchmark", type="primary", use_container_width=True)

with st.spinner("Loading benchmark evaluation results..."):
    report = evaluator.run_benchmark(records=reference_records, persist=run_fresh)

summary = report["reference_summary"]
metrics = report["metrics"]
comparison = report["comparison_table"]
limitations = report["limitations"]

fg_m = metrics["filingguard"]
st_m = metrics["simple_tag"]
llm_m = metrics["llm_baseline"]
reviewer_flag_count = sum(1 for record in reference_records if record.reviewer_verified)
benchmark_coverage = (
    fg_m["predictions_returned"] / fg_m["total_cases"]
    if fg_m["total_cases"]
    else 0.0
)
llm_results = report["detailed_results"]["llm_baseline"]
llm_disclosure = (
    llm_results[0]["notes"]
    if llm_results and llm_results[0].get("notes")
    else "No LLM baseline result was returned."
)

def format_rate(method_metrics, key):
    value = method_metrics[key]
    if value is not None:
        return f"{value * 100:.1f}%"
    return "Not evaluated" if method_metrics["evaluated_cases"] == 0 else "No predictions"


def format_count(method_metrics, key):
    if method_metrics["evaluated_cases"] == 0:
        return "Not evaluated"
    return f"{method_metrics[key]}/{method_metrics['evaluated_cases']}"

# ---------------------------------------------------------------------------
# Section 1: Top KPI Performance Cards
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

with kpi1:
    render_kpi_card(
        label="FilingGuard Accuracy",
        value=f"{fg_m['accuracy'] * 100:.1f}%",
        subtext=f"{fg_m['exact_matches']}/{fg_m['evaluated_cases']} exact matches",
        status="info",
    )

with kpi2:
    render_kpi_card(
        label="FilingGuard Coverage",
        value=f"{benchmark_coverage * 100:.1f}%",
        subtext=f"{fg_m['predictions_returned']}/{fg_m['total_cases']} predictions returned",
        status="info",
    )

with kpi3:
    render_kpi_card(
        label="Reference Dataset",
        value=f"{summary['total_reference_facts']} facts",
        subtext=f"{summary['filing_count']} filings · {summary['metric_coverage_count']} metrics",
        status="neutral",
    )

with kpi4:
    render_kpi_card(
        label="Companies in Reference Set",
        value=str(summary["company_count"]),
        subtext=", ".join(summary["companies"]) or "No companies",
        status="neutral",
    )

with kpi5:
    render_kpi_card(
        label="Reviewer Flags Set",
        value=f"{reviewer_flag_count}/{summary['total_reference_facts']}",
        subtext="Dataset claim; not independently audited",
        status="warning",
    )

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2: Comparative Performance Table
# ---------------------------------------------------------------------------
st.divider()
st.subheader("1. Comparative Extraction Benchmark")
st.caption("Missing predictions count as failures; unavailable baselines are marked not evaluated and have no accuracy rate.")

comp_data = [
    {
        "Evaluation Criterion": "Exact Match Accuracy (Value + Unit + Period)",
        "Baseline A: Simple Tag": f"{format_rate(st_m, 'accuracy')} ({format_count(st_m, 'exact_matches')} exact)",
        "Baseline B: LLM-Only": llm_disclosure,
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": f"{format_rate(fg_m, 'accuracy')} ({format_count(fg_m, 'exact_matches')} exact)",
    },
    {
        "Evaluation Criterion": "Value Match Rate (within ±$1.00)",
        "Baseline A: Simple Tag": f"{format_rate(st_m, 'value_match_rate')} ({format_count(st_m, 'value_matches')} matches)",
        "Baseline B: LLM-Only": llm_disclosure,
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": f"{format_rate(fg_m, 'value_match_rate')} ({format_count(fg_m, 'value_matches')} matches)",
    },
    {
        "Evaluation Criterion": "Period Selection Accuracy",
        "Baseline A: Simple Tag": format_rate(st_m, "period_accuracy"),
        "Baseline B: LLM-Only": llm_disclosure,
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": format_rate(fg_m, "period_accuracy"),
    },
    {
        "Evaluation Criterion": "Unit Standardization Accuracy",
        "Baseline A: Simple Tag": format_rate(st_m, "unit_accuracy"),
        "Baseline B: LLM-Only": llm_disclosure,
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": format_rate(fg_m, "unit_accuracy"),
    },
    {
        "Evaluation Criterion": "Traceable Source Evidence Rate",
        "Baseline A: Simple Tag": f"{format_rate(st_m, 'evidence_support_rate')} (no source-linked evidence)",
        "Baseline B: LLM-Only": "—",
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": f"{format_rate(fg_m, 'evidence_support_rate')} ({fg_m['evidence_supported']}/{fg_m['predictions_returned']} predictions)",
    },
    {
        "Evaluation Criterion": "Missing / Unresolved Value Rate",
        "Baseline A: Simple Tag": f"{format_rate(st_m, 'missing_value_rate')} ({format_count(st_m, 'missing_values')} missing)",
        "Baseline B: LLM-Only": llm_disclosure,
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": f"{format_rate(fg_m, 'missing_value_rate')} ({format_count(fg_m, 'missing_values')} missing)",
    },
    {
        "Evaluation Criterion": "False Positive / Mismatch Rate",
        "Baseline A: Simple Tag": format_rate(st_m, "false_positive_rate"),
        "Baseline B: LLM-Only": "N/A",
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": format_rate(fg_m, "false_positive_rate"),
    },
    {
        "Evaluation Criterion": "Anomaly Precision & Recall",
        "Baseline A: Simple Tag": f"{format_rate(st_m, 'anomaly_precision')} / {format_rate(st_m, 'anomaly_recall')}",
        "Baseline B: LLM-Only": "N/A",
        "Baseline C: Regex/Table": "Not evaluated",
        "FilingGuard (Hybrid)": f"{format_rate(fg_m, 'anomaly_precision')} / {format_rate(fg_m, 'anomaly_recall')}",
    },
]

st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)

if llm_m["not_evaluated_cases"] == llm_m["total_cases"]:
    st.markdown(
        f"""
        <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 0.85rem 1.25rem; margin-top: 0.5rem; margin-bottom: 1rem;">
            <div style="font-weight: 700; color: #1e40af; font-size: 0.88rem;">ℹ️ BASELINE B (LLM-ONLY) METHODOLOGY DISCLOSURE</div>
            <div style="font-size: 0.84rem; color: #1e40af; margin-top: 0.2rem;">
                {escape(llm_disclosure)}
                Unavailable baseline predictions are excluded from accuracy denominators and are not synthesized.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Section 3: Itemized Reference Facts & Side-by-Side Comparison
# ---------------------------------------------------------------------------
st.divider()
st.subheader("2. Itemized Reference Cases & Side-by-Side Extraction")
st.caption("Inspect predictions and linked source evidence; baseline rows marked not evaluated are not scored.")

df_comp = pd.DataFrame(comparison)
df_comp["expected_val_fmt"] = df_comp["expected_value"].apply(lambda v: format_currency(v))
df_comp["simple_val_fmt"] = df_comp["simple_predicted"].apply(lambda v: format_currency(v) if pd.notnull(v) else "Missing")
df_comp["regex_val_fmt"] = "Not evaluated"
df_comp["fg_val_fmt"] = df_comp["fg_predicted"].apply(lambda v: format_currency(v) if pd.notnull(v) else "Missing")
df_comp["simple_status"] = df_comp.apply(
    lambda row: "⚪ Missing" if pd.isna(row["simple_predicted"]) else ("🟢 Match" if row["simple_match"] else "🔴 Mismatch"),
    axis=1,
)
df_comp["regex_status"] = "⚪ Not evaluated"
df_comp["fg_status"] = df_comp.apply(
    lambda row: "⚪ Missing" if pd.isna(row["fg_predicted"]) else ("🟢 Exact Match" if row["fg_match"] else "🔴 Mismatch"),
    axis=1,
)
df_comp["ev_status"] = df_comp["evidence_support"].apply(
    lambda e: "🔗 Traceable" if e else "⚪ No matched evidence"
)

cols_to_display = [
    "test_case_id",
    "company",
    "metric_id",
    "expected_val_fmt",
    "simple_val_fmt",
    "simple_status",
    "regex_val_fmt",
    "regex_status",
    "fg_val_fmt",
    "fg_status",
    "ev_status",
]
col_rename = {
    "test_case_id": "Test Case ID",
    "company": "Ticker",
    "metric_id": "Canonical Metric",
    "expected_val_fmt": "Reference Value",
    "simple_val_fmt": "Simple Tag Value",
    "simple_status": "Simple Tag",
    "regex_val_fmt": "Regex Sim Value",
    "regex_status": "Regex Sim",
    "fg_val_fmt": "FilingGuard Value",
    "fg_status": "FilingGuard",
    "ev_status": "Traceable Source Evidence",
}

df_display = df_comp[cols_to_display].rename(columns=col_rename)

st.dataframe(df_display, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section 4: Breakdown by Metric
# ---------------------------------------------------------------------------
st.divider()
st.subheader("3. Canonical Metric Breakdown")

col_b1, col_b2 = st.columns(2)

with col_b1:
    st.markdown("**FilingGuard Extraction Accuracy by Metric**")
    fg_breakdown = report["per_metric_breakdown"]["filingguard"]
    b_rows_fg = [
        {
            "Metric": k.replace("_", " ").title(),
            "Cases": v["total"],
            "Exact Matches": v["exact_matches"],
            "Accuracy": f"{(v['exact_matches'] / v['total'] * 100):.0f}%" if v["total"] else "N/A",
        }
        for k, v in fg_breakdown.items()
    ]
    st.dataframe(pd.DataFrame(b_rows_fg), use_container_width=True, hide_index=True)

with col_b2:
    st.markdown("**Baseline A (Simple Tag) Accuracy by Metric**")
    st_breakdown = report["per_metric_breakdown"]["simple_tag"]
    b_rows_st = [
        {
            "Metric": k.replace("_", " ").title(),
            "Cases": v["total"],
            "Matches": v["value_matches"],
            "Accuracy": f"{(v['exact_matches'] / v['total'] * 100):.0f}%" if v["total"] else "N/A",
        }
        for k, v in st_breakdown.items()
    ]
    st.dataframe(pd.DataFrame(b_rows_st), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Company-wise performance")
st.caption("Counts and match rates are derived from the loaded reference records for each extraction method.")
company_breakdowns = report["per_company_breakdown"]
company_rows = []
for ticker in summary["companies"]:
    row = {"Company": ticker}
    for method, label in (
        ("filingguard", "FilingGuard"),
        ("simple_tag", "Simple tag"),
        ("regex_simulation", "Regex/Table"),
    ):
        result = company_breakdowns[method].get(ticker)
        if result:
            if result["evaluated"] == 0:
                row[f"{label} exact matches"] = "Not evaluated"
                row[f"{label} missing"] = "Not evaluated"
            else:
                row[f"{label} exact matches"] = f"{result['exact_matches']}/{result['evaluated']}"
                row[f"{label} missing"] = result["missing"]
        else:
            row[f"{label} exact matches"] = "N/A"
            row[f"{label} missing"] = "N/A"
    company_rows.append(row)
st.dataframe(pd.DataFrame(company_rows), use_container_width=True, hide_index=True)

st.subheader("Missing, ambiguous, and mismatched predictions")
fg_details = report["detailed_results"]["filingguard"]
needs_review = [
    result
    for result in fg_details
    if result["predicted_value"] is None
    or result.get("error_type") in ("ambiguous", "ambiguous_mapping")
    or not (
        result["is_value_match"]
        and result["is_unit_match"]
        and result["is_period_match"]
    )
]
if needs_review:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Test case": item["test_case_id"],
                    "Company": item["company"],
                    "Metric": item["metric_id"],
                    "Prediction": (
                        format_currency(item["predicted_value"])
                        if item["predicted_value"] is not None
                        else "Missing"
                    ),
                    "Issue": item.get("error_type") or "mismatch",
                    "Notes": item.get("notes") or "—",
                }
                for item in needs_review
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("No missing, ambiguous, or mismatched FilingGuard predictions in this run.")

st.subheader("Dataset provenance")
source_counts = {}
for record in reference_records:
    source_counts[record.evidence_source] = source_counts.get(record.evidence_source, 0) + 1
source_count_display = ", ".join(
    f"{escape(source)}: {count}" for source, count in sorted(source_counts.items())
) or "None recorded"
st.markdown(
    f"""
    <div class="fg-card">
        <div><strong>Reference facts:</strong> {summary["total_reference_facts"]}</div>
        <div><strong>Reviewer-verified flags:</strong> {reviewer_flag_count} of {summary["total_reference_facts"]} (dataset claims; not independently audited)</div>
        <div><strong>Source URLs:</strong> {summary["source_url_count"]} of {summary["total_reference_facts"]}</div>
        <div><strong>Exact evidence locators:</strong> {summary["evidence_locator_count"]} of {summary["total_reference_facts"]}</div>
        <div><strong>Documented verification methods:</strong> {summary["verification_method_count"]} of {summary["total_reference_facts"]}</div>
        <div><strong>Companies:</strong> {", ".join(summary["companies"]) or "None"}</div>
        <div><strong>Filings:</strong> {summary["filing_count"]}</div>
        <div><strong>Evidence source citations:</strong> {source_count_display}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Section 5: Documented Scope Boundaries & Limitations
# ---------------------------------------------------------------------------
st.divider()
st.subheader("4. Documented Limitations & Scope Boundaries")

lim_html = "".join(
    f"<li style='margin-bottom: 0.35rem; color: #475569;'>{escape(lim)}</li>"
    for lim in limitations
)
st.markdown(
    f"""
    <div class="fg-card">
        <ul style="padding-left: 1.25rem; margin: 0; font-size: 0.92rem; line-height: 1.6;">
            {lim_html}
        </ul>
    </div>
    """,
    unsafe_allow_html=True,
)
