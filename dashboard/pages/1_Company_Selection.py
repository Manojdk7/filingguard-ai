import sys
import logging
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.database.connection import check_db_health
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.filing_repository import FilingRecord, FilingRepository
from app.database.repositories.reconciliation_repository import ReconciliationRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.database.repositories.xbrl_fact_repository import XBRLFactRepository
from app.sec.client import SECClient, SECClientError
from app.sec.filing_download import FilingDownloader
from app.sec.filing_index import FilingIndexResolver
from app.sec.submissions import NoEligibleFilingError, SubmissionsManager
from app.workflow.resume import WorkflowService
from app.extraction.taxonomy_mapping import TaxonomyMappingManager
from dashboard.components.company_data import (
    PRESET_COMPANIES,
    PRESET_OPTIONS,
    QUICK_INGEST_TICKERS,
)
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    format_currency,
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

logger = logging.getLogger("filingguard.dashboard.company_selection")

st.set_page_config(
    page_title="FilingGuard AI - Company Selection & Extraction",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_sidebar_branding()

render_header(
    title="Company Selection & Extraction",
    subtitle="Select an issuer and filing, ingest the official SEC document, then run the evidence-backed extraction and audit workflow.",
    category_chip="WORKSPACE • SEC INGESTION & EXTRACTION",
)

if not check_db_health():
    st.error("Database connection is offline. Please check SQLite database configuration.")
    st.stop()

filing_repo = FilingRepository()
doc_repo = DocumentRepository()
workflow_service = WorkflowService()


def _retrieve_and_store_filing(cik_or_ticker: str) -> FilingRecord:
    sec_client = SECClient()
    sub_mgr = SubmissionsManager(client=sec_client)
    resolver = FilingIndexResolver(client=sec_client)
    downloader = FilingDownloader(client=sec_client)

    cik = sub_mgr.resolve_cik(cik_or_ticker)
    submissions_data = sub_mgr.fetch_submissions(cik)
    filing = sub_mgr.select_latest_10k(submissions_data)
    if not filing:
        raise NoEligibleFilingError(f"No eligible 10-K filing found for CIK {cik}.")

    filing = resolver.resolve_primary_document_url(filing)
    if not filing.primary_doc_url:
        raise SECClientError(
            f"SEC did not provide a primary document URL for {filing.accession_number}."
        )
    filing_repo.save(filing)

    stored_document = doc_repo.get_by_accession(filing.accession_number)
    if (
        not stored_document
        or not Path(stored_document.local_path).is_file()
        or Path(stored_document.local_path).stat().st_size == 0
    ):
        downloaded = downloader.download_filing(filing)
        doc_repo.save_downloaded_document(downloaded)
    return filing


# ---------------------------------------------------------------------------
# Section 1: Target Enterprise Selector
# ---------------------------------------------------------------------------
def _persist_company_preset():
    st.session_state["selected_company_preset"] = st.session_state[
        "company_preset_selector"
    ]


saved_preset = st.session_state.get("selected_company_preset", PRESET_OPTIONS[0])
if saved_preset not in PRESET_COMPANIES:
    saved_preset = PRESET_OPTIONS[0]

col_select, col_search = st.columns([3, 2])

with col_select:
    selected_preset = st.selectbox(
        "Choose Pre-Configured Enterprise Target:",
        options=PRESET_OPTIONS,
        index=PRESET_OPTIONS.index(saved_preset),
        key="company_preset_selector",
        on_change=_persist_company_preset,
    )
    st.session_state["selected_company_preset"] = selected_preset
    preset_meta = PRESET_COMPANIES[selected_preset]
    target_cik = preset_meta["cik"]
    target_ticker = preset_meta["ticker"]

with col_search:
    custom_input = st.text_input(
        "Or Ingest by Custom CIK or Ticker:",
        placeholder="e.g. 0000320193 or AAPL",
        help="Input a 10-digit SEC CIK or official NASDAQ/NYSE ticker.",
    ).strip().upper()

    if custom_input:
        target_ticker = custom_input
        matched = next((m for m in PRESET_COMPANIES.values() if m["ticker"] == custom_input or m["cik"] == custom_input), None)
        if matched:
            target_cik = matched["cik"]
        else:
            target_cik = custom_input.zfill(10) if custom_input.isdigit() else custom_input

cik_label = (
    f"**Normalized SEC CIK**: `{target_cik}`"
    if not custom_input
    else f"**Selected identifier**: `{custom_input}`"
)
industry_label = preset_meta["industry"] if not custom_input else "Custom SEC issuer"
st.caption(f"**Industry Focus**: {industry_label} | {cik_label}")

target_identifier = custom_input or target_ticker
resolved_identifier = st.session_state.get("resolved_selection_identifier")
resolved_cik = st.session_state.get("resolved_selection_cik")
if resolved_identifier == target_identifier and resolved_cik:
    selection_cik = resolved_cik
elif target_cik.isdigit():
    selection_cik = target_cik.zfill(10)
else:
    selection_cik = None

# ---------------------------------------------------------------------------
# Section 2: SEC EDGAR Ingestion Action Bar
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

col_act1, col_act2, col_msg = st.columns([2, 2, 4])

with col_act1:
    if st.button("📥 Retrieve from SEC EDGAR", type="primary", use_container_width=True):
        with st.spinner(f"Resolving {target_identifier} and retrieving its latest 10-K..."):
            try:
                filing = _retrieve_and_store_filing(target_identifier)
                st.session_state["resolved_selection_identifier"] = target_identifier
                st.session_state["resolved_selection_cik"] = filing.cik
                st.success(
                    f"Ingested {filing.company_name or target_identifier} Form 10-K "
                    f"(`{filing.accession_number}`)."
                )
                st.rerun()
            except Exception as e:
                logger.exception("SEC retrieval failed for %s", target_identifier)
                st.error(f"SEC retrieval failed: {str(e)}")

with col_act2:
    if st.button("⚡ Quick Ingest 6 Demo Targets", use_container_width=True):
        results = []
        failures = []
        progress = st.progress(0, text="Retrieving official filings for preset companies...")
        targets = [
            (label, company)
            for label, company in PRESET_COMPANIES.items()
            if company["ticker"] in QUICK_INGEST_TICKERS
        ]
        for index, (company_label, company) in enumerate(targets, start=1):
            try:
                filing = _retrieve_and_store_filing(company["cik"])
                results.append(
                    f"{company_label}: {filing.accession_number}"
                )
            except Exception as e:
                logger.exception("SEC retrieval failed for demo target %s", company_label)
                failures.append(f"{company_label}: {e}")
            progress.progress(
                index / len(targets),
                text=f"Processed {company_label} ({index}/{len(targets)})",
            )
        if results:
            st.success(f"Retrieved or verified {len(results)} official SEC filings.")
            with st.expander("Successful filings"):
                st.markdown("\n".join(f"- {item}" for item in results))
        if failures:
            st.error(f"Could not retrieve {len(failures)} of {len(targets)} filings.")
            with st.expander("Retrieval errors", expanded=True):
                st.markdown("\n".join(f"- {item}" for item in failures))

with col_msg:
    st.markdown(
        "<div style='font-size: 0.85rem; color: #64748b; line-height: 1.4; padding-top: 0.4rem;'>"
        "SEC Fair-Access policy enforced (&lt;10 req/sec) with automated exponential backoff and local SHA-256 disk caching."
        "</div>",
        unsafe_allow_html=True,
    )

if not selection_cik and custom_input:
    st.info("Retrieve this ticker first to resolve its SEC CIK before selecting an extraction filing.")

# ---------------------------------------------------------------------------
# Section 3: Workflow Launcher Card
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Extract Financial Data & Run Audit Workflow")
st.caption("Runs the existing SEC retrieval, Company Facts and Inline XBRL extraction, reconciliation, scoring, validation, and human-review routing stages.")

all_filings = filing_repo.get_recent_filings(limit=50)
company_filings = [
    filing for filing in all_filings
    if selection_cik and filing.cik.zfill(10) == selection_cik
]

if company_filings:
    accn_options = {
        f"{f.company_name} ({f.ticker or 'N/A'}) - 10-K [{f.report_period or f.filing_date}] — Accn: {f.accession_number}": f.accession_number
        for f in company_filings
    }
    if st.session_state.get("company_extraction_filing") not in accn_options:
        st.session_state.pop("company_extraction_filing", None)
    last_extraction_accn = st.session_state.get("last_extraction_accession")
    default_run_index = next(
        (index for index, accession in enumerate(accn_options.values()) if accession == last_extraction_accn),
        0,
    )
    selected_run_label = st.selectbox(
        "Select filing to extract:",
        options=list(accn_options.keys()),
        index=default_run_index,
        key="company_extraction_filing",
    )
    selected_run_accn = accn_options[selected_run_label]

    col_btn_run, col_guidance = st.columns([3, 4])

    with col_btn_run:
        if st.button("⚡ Extract Financial Data", type="primary", use_container_width=True):
            target_filing_record = filing_repo.get_by_accession(selected_run_accn)
            thread_id = f"thread_{selected_run_accn}"
            with st.spinner(f"Running LangGraph workflow on thread `{thread_id}`..."):
                t_id, state = workflow_service.start_workflow(
                    accession_number=selected_run_accn,
                    cik=target_filing_record.cik if target_filing_record else None,
                    thread_id=thread_id,
                )
                extraction_result = state.get("extraction_result") or {}
                st.session_state["last_extraction_accession"] = selected_run_accn
                st.session_state["last_extraction_status"] = extraction_result.get("status", "not_run")
                st.session_state["last_extraction_workflow_status"] = state.get("workflow_status", "UNKNOWN")
                st.session_state["last_extraction_errors"] = state.get("errors", [])
                status = state.get("workflow_status")
                if status == "PAUSED_FOR_REVIEW":
                    st.warning(f"Workflow paused at **Human Review Gate** on thread `{t_id}`. Please navigate to **4. Human Review** to approve or correct.")
                elif status == "COMPLETED":
                    st.success(f"Extraction and workflow completed on thread `{t_id}`.")
                else:
                    st.info(f"Workflow status: `{status}`.")

            with st.expander("📜 View Workflow Stage Execution Log", expanded=True):
                for log_msg in state.get("execution_log", []):
                    st.text(log_msg)

    with col_guidance:
        st.markdown(
            """
            <div class="fg-card" style="margin-bottom: 0;">
                <div style="font-weight: 700; color: #101b32; margin-bottom: 0.4rem; font-size: 0.92rem;">Workflow stages</div>
                <div style="font-size: 0.85rem; color: #475569; line-height: 1.6;">
                    • <b>Extraction</b>: Compare selected Company Facts with Inline XBRL data.<br>
                    • <b>3. Validation</b>: Review the 14 accounting rule checks and YoY variance flags.<br>
                    • <b>4. Human Review</b>: If paused, approve or correct disputed metrics with mandatory audit rationale.<br>
                    • <b>6. Audit History</b>: Inspect the cryptographic SHA-256 hash chain.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    active_extraction_accn = st.session_state.get("last_extraction_accession")
    if active_extraction_accn == selected_run_accn:
        if st.session_state.get("last_extraction_status") == "success":
            st.divider()
            st.subheader("Extracted financial data")
            st.caption(
                f"Results are loaded from persisted extraction, reconciliation, and scoring records for accession {active_extraction_accn}."
            )

            fact_repo = FactRepository()
            xbrl_repo = XBRLFactRepository()
            reconciliation_repo = ReconciliationRepository()
            scoring_repo = ScoringRepository()
            taxonomy_manager = TaxonomyMappingManager()

            selected_facts = fact_repo.get_all_facts_by_accession(active_extraction_accn)
            ixbrl_facts = xbrl_repo.get_facts_by_accession(active_extraction_accn)
            reconciliations = reconciliation_repo.get_reconciliations_by_accession(active_extraction_accn)
            metric_scores = scoring_repo.get_metric_scores_by_accession(active_extraction_accn)

            facts_by_metric = {}
            for fact in selected_facts:
                if fact.metric_id not in facts_by_metric or fact.status == "selected":
                    facts_by_metric[fact.metric_id] = fact
            recons_by_metric = {item.metric_id: item for item in reconciliations}
            scores_by_metric = {item.metric_id: item for item in metric_scores}

            metric_definitions = taxonomy_manager.get_all_metrics()
            metric_columns = st.columns(4)
            for index, metric in enumerate(metric_definitions):
                fact = facts_by_metric.get(metric.metric_id)
                score = scores_by_metric.get(metric.metric_id)
                value = format(
                    fact.normalized_value,
                    ",.0f",
                ) if fact and fact.status == "selected" else "Not selected"
                if fact and fact.unit and fact.unit.upper() in ("USD", "US DOLLARS"):
                    value = f"${value}" if value != "Not selected" else value
                with metric_columns[index % len(metric_columns)]:
                    render_kpi_card(
                        label=metric.canonical_name,
                        value=value,
                        subtext=(
                            f"Quality {score.quality_score_100:.1f}/100"
                            if score
                            else (fact.status.replace("_", " ").title() if fact else "Missing")
                        ),
                        status=(
                            "success"
                            if fact and fact.status == "selected"
                            else ("warning" if fact else "danger")
                        ),
                    )

            tab_metrics, tab_reconciliation, tab_evidence = st.tabs(
                ["Metric coverage", "Company Facts vs Inline XBRL", "Source evidence"]
            )

            with tab_metrics:
                metric_rows = []
                for metric in metric_definitions:
                    fact = facts_by_metric.get(metric.metric_id)
                    recon = recons_by_metric.get(metric.metric_id)
                    score = scores_by_metric.get(metric.metric_id)
                    metric_rows.append(
                        {
                            "Metric": metric.canonical_name,
                            "Status": fact.status if fact else "missing",
                            "Selected value": (
                                format_currency(fact.normalized_value)
                                if fact and fact.status == "selected"
                                else "—"
                            ),
                            "Unit": fact.unit if fact else "—",
                            "Concept": fact.concept if fact else "—",
                            "Candidates": sum(1 for item in selected_facts if item.metric_id == metric.metric_id),
                            "Inline XBRL": (
                                recon.status.replace("_", " ")
                                if recon
                                else "not reconciled"
                            ),
                            "Confidence": (
                                f"{score.quality_score_100:.1f}/100"
                                if score
                                else "—"
                            ),
                        }
                    )
                st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)

                ambiguous_facts = [fact for fact in selected_facts if fact.status == "ambiguous"]
                missing_metrics = [
                    metric.canonical_name
                    for metric in metric_definitions
                    if metric.metric_id not in facts_by_metric
                ]
                if ambiguous_facts:
                    st.warning(f"{len(ambiguous_facts)} ambiguous fact candidate(s) require inspection; none were promoted automatically.")
                if missing_metrics:
                    st.info(f"Metrics with no stored candidate: {', '.join(missing_metrics)}.")

            with tab_reconciliation:
                if reconciliations:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Metric": item.canonical_name,
                                    "Status": item.status.replace("_", " "),
                                    "Company Facts": format_currency(item.company_facts_value),
                                    "Inline XBRL": format_currency(item.ixbrl_value),
                                    "Difference": format_currency(item.difference),
                                    "CF concept": item.company_facts_concept or "—",
                                    "iXBRL concept": item.ixbrl_concept or "—",
                                    "Explanation": item.explanation,
                                }
                                for item in reconciliations
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No cross-source reconciliation records were produced for this filing.")

            with tab_evidence:
                st.write(
                    f"Persisted SEC Company Facts: {len(selected_facts)} candidate/selected records · "
                    f"Parsed Inline XBRL: {len(ixbrl_facts)} facts · "
                    f"Reconciliation records: {len(reconciliations)}."
                )
                for metric in metric_definitions:
                    metric_id = metric.metric_id
                    fact = facts_by_metric.get(metric_id)
                    score = scores_by_metric.get(metric_id)
                    matching_xbrl = [
                        item
                        for item in ixbrl_facts
                        if fact and item.concept_name == fact.concept
                    ]
                    with st.expander(metric.canonical_name):
                        if fact:
                            st.markdown(
                                f"**Company Facts:** `{fact.concept}` · {format_currency(fact.raw_value)} {fact.unit} · "
                                f"{fact.period_start or 'instant'} to {fact.period_end} · status `{fact.status}`"
                            )
                            st.caption(fact.selection_explanation)
                        else:
                            st.info("No Company Facts candidate was persisted for this metric.")
                        if score:
                            st.json(score.evidence_references)
                        if matching_xbrl:
                            st.dataframe(
                                pd.DataFrame(
                                    [
                                        {
                                            "Concept": item.concept_name,
                                            "Value": item.value,
                                            "Context": item.context_id,
                                            "Period end": item.end_date,
                                            "Segment": item.is_segment,
                                            "Source locator": item.source_locator,
                                            "SHA-256": item.source_doc_hash,
                                        }
                                        for item in matching_xbrl
                                    ]
                                ),
                                use_container_width=True,
                                hide_index=True,
                            )
                        elif ixbrl_facts:
                            st.caption("No exact concept-name match in the parsed Inline XBRL facts.")
        elif st.session_state.get("last_extraction_status") != "not_run":
            st.error(
                "The workflow did not complete its extraction stage. No extraction results are shown."
            )
            workflow_errors = st.session_state.get("last_extraction_errors", [])
            if workflow_errors:
                for error in workflow_errors:
                    st.caption(error)
else:
    st.info(
        "No locally ingested filings are available for the selected company. "
        "Retrieve its SEC filing above before starting extraction."
    )
