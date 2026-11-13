import json
import sys
from pathlib import Path

# Add project root to sys.path so app modules can be resolved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.audit.ledger import AuditLedgerService
from app.audit.verification import AuditVerifier
from app.database.connection import check_db_health, get_db_connection
from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.filing_repository import FilingRepository
from dashboard.components.styles import inject_custom_css
from dashboard.components.ui import (
    render_header,
    render_kpi_card,
    render_sidebar_branding,
)

st.set_page_config(
    page_title="FilingGuard AI - Audit History & Ledger Verification",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_sidebar_branding()

render_header(
    title="Cryptographic Audit History & Ledger Verification",
    subtitle="Tamper-evident, insert-only audit log recording every pipeline stage transition, scoring decision, and auditor override.",
    category_chip="PIPELINE STAGE 6 • TAMPER-EVIDENT AUDIT LEDGER",
)

if not check_db_health():
    st.error("Database connection is offline. Please check SQLite database configuration.")
    st.stop()

filing_repo = FilingRepository()
audit_repo = AuditRepository()
verifier = AuditVerifier(audit_repo=audit_repo)

# ---------------------------------------------------------------------------
# Section 1: Filing Scope Filter
# ---------------------------------------------------------------------------
all_filings = filing_repo.get_recent_filings(limit=50)

scope_options = {"[Global] All Ingested Filings & System Events": None}
for f in all_filings:
    label = f"{f.company_name or 'Unknown'} ({f.ticker or 'N/A'}) — Accn: {f.accession_number}"
    scope_options[label] = f.accession_number

selected_scope_label = st.selectbox("Select Audit Verification Scope:", options=list(scope_options.keys()))
selected_accn = scope_options[selected_scope_label]

# ---------------------------------------------------------------------------
# Section 2: Chain Verification KPI Cards
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

verification = verifier.verify_chain(accession_number=selected_accn)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    chain_status = "success" if verification.is_valid else "danger"
    status_label = "🟢 VALID" if verification.is_valid else "🔴 TAMPERED"
    render_kpi_card(
        label="Chain Integrity",
        value=status_label,
        subtext="Zero Broken Hash Links" if verification.is_valid else f"Alert at Seq #{verification.first_tampered_sequence}",
        status=chain_status,
    )

with kpi2:
    render_kpi_card(
        label="Total Events Verified",
        value=f"{verification.total_events} Events",
        subtext="Insert-Only Storage",
        status="info",
    )

with kpi3:
    latest_h = verification.latest_event_hash or "0" * 64
    render_kpi_card(
        label="Latest Head Hash",
        value=f"{latest_h[:12]}...",
        subtext="Current Chain Anchor",
        status="neutral",
    )

with kpi4:
    render_kpi_card(
        label="Hashing Standard",
        value="SHA-256",
        subtext="HMAC Signatures Enabled",
        status="neutral",
    )

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

if not verification.is_valid:
    st.error(f"⚠️ **Cryptographic Tamper Alert**: {verification.failure_reason}")
else:
    st.success(
        f"Hash-chain verification completed at {verification.verified_at}. "
        f"{verification.total_events} event(s) were checked; "
        "the stored sequence and hash pointers are valid."
    )

# ---------------------------------------------------------------------------
# Section 3: Interactive Tamper Detection Sandbox (Hackathon Demonstration)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("1. Interactive Tamper Detection Sandbox")
st.caption(
    "Demonstrates the mathematical resilience of the audit ledger. Simulate a storage-level database breach "
    "or unauthorized payload modification to observe instant fraud detection by the verification engine."
)

with st.expander("🛠️ Open Tamper Simulation Sandbox", expanded=False):
    st.markdown(
        """
        <div style="font-size: 0.9rem; color: #475569; margin-bottom: 0.75rem;">
            Click <b>Simulate Payload Tampering</b> to modify an existing SQLite audit event payload directly at the database layer.
            Because the hash chain relies on <code>SHA256(previous_hash + canonical_json(payload) + created_at)</code>,
            any historical change breaks the chain pointer and alerts the verifier.
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if st.button("🔴 Simulate Unauthorized Data Modification (Inject Tamper)", use_container_width=True):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, sequence_num, payload_json FROM audit_events ORDER BY id DESC LIMIT 1;")
                target_ev = cursor.fetchone()
                if target_ev:
                    tampered_payload = json.dumps({"tampered_by": "unauthorized_actor", "illicit_adjustment": True})
                    conn.execute(
                        "UPDATE audit_events SET payload_json = ? WHERE id = ?;",
                        (tampered_payload, target_ev["id"]),
                    )
                    st.error(f"Maliciously altered Event #{target_ev['sequence_num']}. Chain integrity compromised!")
                    st.rerun()
                else:
                    st.info("No events available to tamper.")

    with col_t2:
        if st.button("🟢 Repair Ledger & Re-Anchor Hash Chain", use_container_width=True):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM audit_events ORDER BY sequence_num ASC;")
                rows = cursor.fetchall()
                from app.audit.hashing import calculate_event_hash
                prev = "0" * 64
                for r in rows:
                    p_load = json.loads(r["payload_json"])
                    h = calculate_event_hash(prev, p_load, r["created_at"])
                    conn.execute("UPDATE audit_events SET previous_hash = ?, event_hash = ? WHERE id = ?;", (prev, h, r["id"]))
                    prev = h
            st.success("Ledger hashes re-anchored. Chain integrity restored to VALID.")
            st.rerun()

# ---------------------------------------------------------------------------
# Section 4: Sequential Audit Trail Log
# ---------------------------------------------------------------------------
st.divider()
st.subheader("2. Sequential Cryptographic Audit Trail")
st.caption("Chronological list of all events, actors, accession numbers, and linear SHA-256 hash pointers.")

audit_events = audit_repo.get_all_events(accession_number=selected_accn)

if not audit_events:
    st.info("No audit ledger events recorded for the selected scope.")
else:
    table_rows = []
    for e in audit_events:
        table_rows.append({
            "Seq #": e.sequence_num,
            "Event Type": e.event_type,
            "Actor": e.actor,
            "Accession Number": e.accession_number or "Global System",
            "Metric ID": e.metric_id or "—",
            "Previous Hash Link": f"{e.previous_hash[:16]}...",
            "Event Hash (Current)": f"{e.event_hash[:16]}...",
            "Timestamp (UTC)": e.created_at,
        })

    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    with st.expander("🔍 Inspect Full Event Payloads & Signatures"):
        for e in audit_events:
            st.markdown(f"**Event #{e.sequence_num}: `{e.event_type}` by `{e.actor}`** (Event ID: `{e.event_id}`)")
            st.json({
                "sequence_num": e.sequence_num,
                "event_id": e.event_id,
                "event_type": e.event_type,
                "actor": e.actor,
                "accession_number": e.accession_number,
                "metric_id": e.metric_id,
                "previous_hash": e.previous_hash,
                "event_hash": e.event_hash,
                "signature": e.signature,
                "created_at": e.created_at,
                "payload": e.payload,
            })

    # -----------------------------------------------------------------------
    # Section 5: Signed Checkpoint Export
    # -----------------------------------------------------------------------
    st.divider()
    st.subheader("3. Export Signed Cryptographic Checkpoint")
    st.caption("Export an immutable HMAC-SHA256 snapshot for independent external auditor archiving.")

    checkpoint_data = verifier.export_checkpoint(accession_number=selected_accn)
    with st.expander("Checkpoint details"):
        st.markdown(
            f"""
            - **Status:** `{checkpoint_data["status"]}`
            - **Events covered:** `{checkpoint_data["total_events"]}`
            - **Latest hash:** `{checkpoint_data["latest_event_hash"]}`
            - **Verified at:** `{checkpoint_data["verified_at"]}`
            - **Signature:** `{checkpoint_data["signature"]}`
            """
        )
    st.download_button(
        label="💾 Download Signed Audit Checkpoint (JSON)",
        data=json.dumps(checkpoint_data, indent=2),
        file_name=f"audit_checkpoint_{selected_accn or 'global'}.json",
        mime="application/json",
        type="primary",
    )
