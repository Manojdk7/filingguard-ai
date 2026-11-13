import sys
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.config import settings
from app.database.connection import check_db_health
from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.filing_repository import FilingRepository
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

st.set_page_config(
    page_title="FilingGuard AI - Enterprise Audit Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply enterprise styling and sidebar branding
inject_custom_css()
render_sidebar_branding()

# Page Header
render_header(
    title="FilingGuard AI",
    subtitle="Evidence-linked financial filing review, deterministic validation, and tamper-evident audit history.",
    category_chip="ENTERPRISE AUDIT PLATFORM • OVERVIEW",
)

# ---------------------------------------------------------------------------
# Section 1: System Status & Infrastructure KPIs
# ---------------------------------------------------------------------------
db_ok = check_db_health()
filing_repo = FilingRepository()
audit_repo = AuditRepository()

filings_count = len(filing_repo.get_recent_filings(limit=100))
events_count = len(audit_repo.get_all_events())

c1, c2, c3, c4 = st.columns(4)
with c1:
    render_kpi_card(
        label="Environment",
        value=settings.APP_ENV.upper(),
        subtext="Deterministic Sandbox",
        status="info",
    )
with c2:
    render_kpi_card(
        label="Database Status",
        value="ONLINE" if db_ok else "OFFLINE",
        subtext="SQLite WAL Engine",
        status="success" if db_ok else "danger",
    )
with c3:
    render_kpi_card(
        label="Ingested Filings",
        value=str(filings_count),
        subtext="SEC Form 10-K Archived",
        status="neutral",
    )
with c4:
    render_kpi_card(
        label="Audit Trail Events",
        value=str(events_count),
        subtext="SHA-256 Hash Chained",
        status="success",
    )

st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2: Interactive Workflow Modules Grid
# ---------------------------------------------------------------------------
st.subheader("Auditing Pipeline Navigation")
st.caption("FilingGuard AI operates an end-to-end deterministic audit workflow with durable LangGraph checkpointing and human oversight.")

col_w1, col_w2 = st.columns(2)

with col_w1:
    st.markdown(
        """
        <div class="fg-card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-size: 1.05rem; font-weight: 700; color: #101b32;">🏢 1. Company Selection & Ingestion</span>
                <span class="fg-badge fg-badge-info">Phase 2</span>
            </div>
            <p style="margin-bottom: 0.85rem; font-size: 0.92rem; color: #475569;">
                Select target public enterprises (Apple, Microsoft, Amazon, Nvidia), download official SEC Form 10-K filings,
                verify primary document SHA-256 integrity hashes, and launch the LangGraph workflow.
            </p>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1d4ed8;">Open Page: 1_Company_Selection in sidebar →</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="fg-card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-size: 1.05rem; font-weight: 700; color: #101b32;">📊 2. Extraction & Confidence Scoring</span>
                <span class="fg-badge fg-badge-info">Phases 3–6</span>
            </div>
            <p style="margin-bottom: 0.85rem; font-size: 0.92rem; color: #475569;">
                Extract 10 canonical financial metrics from SEC Company Facts and Inline XBRL. Review deterministic
                cross-source reconciliation and composite 5-factor quality scores (Evidence 30%, Mapping 25%, Period 20%, Unit 10%, Cross-Check 15%).
            </p>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1d4ed8;">Open Page: 2_Extraction_Results in sidebar →</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="fg-card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-size: 1.05rem; font-weight: 700; color: #101b32;">⚖️ 3. Financial Validation Engine</span>
                <span class="fg-badge fg-badge-info">Phase 7</span>
            </div>
            <p style="margin-bottom: 0.85rem; font-size: 0.92rem; color: #475569;">
                Execute 14 deterministic accounting validation rules: Balance Sheet Equation ($Assets = Liabilities + Equity$),
                Operating Income Presentation, 10 YoY variance threshold alerts, and cross-statement consistency.
            </p>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1d4ed8;">Open Page: 3_Validation in sidebar →</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_w2:
    st.markdown(
        """
        <div class="fg-card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-size: 1.05rem; font-weight: 700; color: #101b32;">🛡️ 4. Human Review & Workflow Gate</span>
                <span class="fg-badge fg-badge-warning">Phases 8–9</span>
            </div>
            <p style="margin-bottom: 0.85rem; font-size: 0.92rem; color: #475569;">
                Inspect escalated metrics at the LangGraph <code>interrupt()</code> gate. Submit auditor approvals, corrections,
                or rejections with mandatory audit justification, idempotency keys, and automated validation recalculation.
            </p>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1d4ed8;">Open Page: 4_Human_Review in sidebar →</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="fg-card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-size: 1.05rem; font-weight: 700; color: #101b32;">📈 5. Benchmark & Accuracy Report</span>
                <span class="fg-badge fg-badge-success">Phase 11</span>
            </div>
            <p style="margin-bottom: 0.85rem; font-size: 0.92rem; color: #475569;">
                Review benchmark results against the configured SEC reference dataset and compare the available extraction baselines.
            </p>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1d4ed8;">Open Page: 5_Accuracy_Report in sidebar →</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="fg-card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-size: 1.05rem; font-weight: 700; color: #101b32;">📜 6. Cryptographic Audit Ledger</span>
                <span class="fg-badge fg-badge-success">Phase 10</span>
            </div>
            <p style="margin-bottom: 0.85rem; font-size: 0.92rem; color: #475569;">
                Inspect verifiable, insert-only audit event history. Test the interactive tamper detection sandbox to verify
                mathematical detection of storage-level data manipulation, and export signed HMAC checkpoints.
            </p>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1d4ed8;">Open Page: 6_Audit_History in sidebar →</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Section 3: Architecture Principles Footer
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
st.markdown(
    """
    <div class="fg-card" style="background: linear-gradient(120deg, #eff6ff, #f0fdfa);">
        <div style="font-weight: 700; color: #101b32; margin-bottom: 0.35rem; font-size: 0.92rem;">
            🔒 ZERO-HALLUCINATION ARCHITECTURAL GUARANTEE
        </div>
        <div style="font-size: 0.88rem; color: #475569; line-height: 1.5;">
            FilingGuard AI never uses generative LLM prompts to synthesize financial statement figures or determine validation pass/fail states.
            All reported values are traced via exact primary document byte offsets and SHA-256 hashes to official SEC EDGAR disclosures.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
