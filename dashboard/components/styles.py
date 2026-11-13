"""
Global enterprise design system and CSS styling for FilingGuard AI.
Provides clean typography, card containers, badge pills, and balanced spacing.
"""
import streamlit as st


def inject_custom_css():
    """Inject global CSS rules to transform Streamlit into an enterprise financial dashboard."""
    st.markdown(
        """
        <style>
        /* -------------------------------------------------------------
           1. ROOT VARIABLES & GLOBAL RESETS
           ------------------------------------------------------------- */
        :root {
            --primary-navy: #101b32;
            --secondary-slate: #253858;
            --primary-blue: #3b82f6;
            --accent-teal: #14b8a6;
            --surface-bg: #f3f6fb;
            --surface-card: #ffffff;
            --border-neutral: #e2e8f0;
            --border-subtle: #cbd5e1;
            --text-main: #101b32;
            --text-muted: #475569;
            --text-subtle: #64748b;
            --success-bg: #ecfdf5;
            --success-border: #a7f3d0;
            --success-text: #065f46;
            --warning-bg: #fffbeb;
            --warning-border: #fde68a;
            --warning-text: #92400e;
            --danger-bg: #fef2f2;
            --danger-border: #fecaca;
            --danger-text: #991b1b;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        .stApp {
            background: var(--surface-bg) !important;
        }

        /* Desktop full-width layout with professional margins */
        .block-container {
            max-width: 100% !important;
            width: 100% !important;
            padding-top: 1.75rem !important;
            padding-bottom: 3rem !important;
            padding-left: clamp(1.25rem, 2.4vw, 2.5rem) !important;
            padding-right: clamp(1.25rem, 2.4vw, 2.5rem) !important;
        }

        /* -------------------------------------------------------------
           2. TYPOGRAPHY & HEADINGS
           ------------------------------------------------------------- */
        h1, h2, h3, h4, h5, h6 {
            font-family: var(--font-family) !important;
            color: var(--text-main) !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em !important;
        }

        h1 {
            font-size: 1.85rem !important;
            line-height: 1.25 !important;
            margin-bottom: 0.35rem !important;
        }

        h2 {
            font-size: 1.35rem !important;
            line-height: 1.3 !important;
            margin-top: 1.25rem !important;
            margin-bottom: 0.65rem !important;
        }

        h3 {
            font-size: 1.15rem !important;
            line-height: 1.35 !important;
            margin-top: 1rem !important;
            margin-bottom: 0.5rem !important;
        }

        p, label {
            font-family: var(--font-family) !important;
            color: var(--text-muted);
            font-size: 0.95rem;
            line-height: 1.55;
        }

        [data-testid="stCaptionContainer"] p {
            color: var(--text-subtle) !important;
        }

        /* Consistent page title treatment */
        .fg-page-header {
            padding: 1.15rem 1.35rem 1.25rem;
            margin-bottom: 1.5rem;
            border: 1px solid rgba(203, 213, 225, 0.75);
            border-radius: 16px;
            background: linear-gradient(120deg, rgba(255,255,255,0.96), rgba(239,246,255,0.84));
            box-shadow: 0 8px 22px rgba(16, 27, 50, 0.045);
        }

        .fg-page-heading {
            display: flex;
            align-items: flex-start;
            gap: 0.9rem;
        }

        .fg-page-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 2.6rem;
            width: 2.6rem;
            height: 2.6rem;
            border-radius: 12px;
            background: #eaf2ff;
            color: var(--primary-blue);
            font-size: 1.2rem;
        }

        .fg-page-heading h1 {
            margin: 0.1rem 0 0.2rem !important;
        }

        .fg-page-heading p {
            margin: 0;
            color: var(--text-muted);
        }

        /* -------------------------------------------------------------
           3. ENTERPRISE CARDS & CONTAINERS
           ------------------------------------------------------------- */
        .fg-card {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid rgba(203, 213, 225, 0.8);
            border-radius: 14px;
            padding: 1.25rem 1.35rem;
            margin-bottom: 1rem;
            box-shadow: 0 5px 16px rgba(16, 27, 50, 0.045);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .fg-card:hover {
            border-color: #bfcee0;
            box-shadow: 0 8px 22px rgba(16, 27, 50, 0.07);
        }

        .fg-card-compact {
            padding: 1rem 1.15rem;
            margin-bottom: 0.75rem;
        }

        /* -------------------------------------------------------------
           4. METRIC KPI CARDS
           ------------------------------------------------------------- */
        .fg-kpi-container {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            background-color: var(--surface-card);
            border: 1px solid var(--border-neutral);
            border-radius: 14px;
            padding: 1.15rem 1.25rem;
            min-height: 116px;
            box-shadow: 0 5px 16px rgba(16, 27, 50, 0.045);
            border-top: 3px solid var(--primary-navy);
        }

        .fg-kpi-success { border-top-color: #10b981 !important; }
        .fg-kpi-warning { border-top-color: #f59e0b !important; }
        .fg-kpi-danger  { border-top-color: #ef4444 !important; }
        .fg-kpi-info    { border-top-color: var(--primary-blue) !important; }

        .fg-kpi-label {
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
            color: var(--text-subtle) !important;
            margin-bottom: 0.25rem !important;
        }

        .fg-kpi-value {
            font-size: 1.65rem !important;
            font-weight: 700 !important;
            color: var(--text-main) !important;
            line-height: 1.2 !important;
            margin: 0.15rem 0 !important;
        }

        .fg-kpi-subtext {
            font-size: 0.82rem !important;
            color: var(--text-muted) !important;
            margin-top: 0.25rem !important;
        }

        /* -------------------------------------------------------------
           5. BADGES & STATUS PILLS
           ------------------------------------------------------------- */
        .fg-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.78rem;
            font-weight: 600;
            padding: 0.25rem 0.65rem;
            border-radius: 9999px;
            line-height: 1;
            letter-spacing: 0.02em;
        }

        .fg-badge-success {
            background-color: var(--success-bg);
            border: 1px solid var(--success-border);
            color: var(--success-text);
        }

        .fg-badge-warning {
            background-color: var(--warning-bg);
            border: 1px solid var(--warning-border);
            color: var(--warning-text);
        }

        .fg-badge-danger {
            background-color: var(--danger-bg);
            border: 1px solid var(--danger-border);
            color: var(--danger-text);
        }

        .fg-badge-info {
            background-color: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #1e40af;
        }

        .fg-badge-neutral {
            background-color: #f1f5f9;
            border: 1px solid #e2e8f0;
            color: #334155;
        }

        /* -------------------------------------------------------------
           6. STREAMLIT EXPANDERS & TABS
           ------------------------------------------------------------- */
        .streamlit-expanderHeader {
            font-family: var(--font-family) !important;
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            color: var(--text-main) !important;
            background-color: #f8fafc !important;
            border-radius: 8px !important;
            padding: 0.75rem 1rem !important;
            border: 1px solid var(--border-neutral) !important;
        }

        div[data-testid="stExpander"] {
            border: none !important;
            margin-bottom: 0.75rem !important;
        }

        div[data-testid="stExpanderDetails"] {
            background-color: var(--surface-card) !important;
            border: 1px solid var(--border-neutral) !important;
            border-top: none !important;
            border-bottom-left-radius: 8px !important;
            border-bottom-right-radius: 8px !important;
            padding: 1.25rem !important;
        }

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px !important;
            border-bottom: 1px solid var(--border-neutral) !important;
            padding-bottom: 2px !important;
        }

        .stTabs [data-baseweb="tab"] {
            font-family: var(--font-family) !important;
            font-weight: 600 !important;
            font-size: 0.92rem !important;
            color: var(--text-muted) !important;
            padding: 0.6rem 1.15rem !important;
            border-radius: 6px 6px 0 0 !important;
        }

        .stTabs [aria-selected="true"] {
            color: var(--primary-blue) !important;
            border-bottom: 2px solid var(--primary-blue) !important;
            background-color: rgba(29, 78, 216, 0.04) !important;
        }

        /* -------------------------------------------------------------
           7. BUTTONS & INPUTS
           ------------------------------------------------------------- */
        .stButton button {
            font-family: var(--font-family) !important;
            font-weight: 600 !important;
            font-size: 0.9rem !important;
            border-radius: 9px !important;
            padding: 0.5rem 1.25rem !important;
            transition: all 0.15s ease !important;
        }

        .stButton button[kind="primary"],
        .stButton button[kind="primary"]:disabled,
        .stButton button[data-testid="stBaseButton-primary"] {
            background-color: #bfdbfe !important;
            border-color: #93c5fd !important;
            color: #1e3a8a !important;
            -webkit-text-fill-color: #1e3a8a !important;
            opacity: 1 !important;
        }

        .stButton button[kind="primary"]:hover,
        .stButton button[data-testid="stBaseButton-primary"]:hover {
            background-color: #93c5fd !important;
            border-color: #60a5fa !important;
            box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.15) !important;
        }

        /* -------------------------------------------------------------
           8. DATAFRAMES & TABLES
           ------------------------------------------------------------- */
        div[data-testid="stDataFrame"] {
            width: 100% !important;
            border: 1px solid var(--border-neutral) !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03) !important;
        }

        /* -------------------------------------------------------------
           9. SIDEBAR & DESKTOP LAYOUT
           ------------------------------------------------------------- */
        section[data-testid="stSidebar"] {
            width: 272px !important;
            min-width: 272px !important;
            background: linear-gradient(180deg, #101b32 0%, #0c1527 100%) !important;
            border-right: 1px solid #253858 !important;
        }

        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            padding-top: 0.35rem;
        }

        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
            margin: 0.15rem 0.5rem;
            border-radius: 9px;
            color: #cbd5e1 !important;
            transition: background-color 0.15s ease, color 0.15s ease;
        }

        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {
            background: rgba(59, 130, 246, 0.14) !important;
            color: #ffffff !important;
        }

        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: rgba(59, 130, 246, 0.22) !important;
            box-shadow: inset 3px 0 0 #3b82f6;
            color: #ffffff !important;
        }

        .fg-sidebar-brand {
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.045);
            padding: 0.9rem;
            margin-top: 1.5rem;
        }

        .fg-sidebar-brand-row {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .fg-sidebar-logo {
            font-size: 1.65rem;
            line-height: 1;
        }

        .fg-sidebar-title {
            color: #f8fafc !important;
            font-size: 1rem;
            font-weight: 700;
        }

        .fg-sidebar-subtitle {
            color: #94a3b8 !important;
            font-size: 0.68rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .fg-sidebar-badges {
            display: flex;
            gap: 0.4rem;
            margin-top: 0.85rem;
        }

        .fg-sidebar-badge {
            border-radius: 6px;
            padding: 0.18rem 0.45rem;
            font-size: 0.66rem;
            font-weight: 600;
        }

        .fg-sidebar-badge-version {
            color: #bfdbfe !important;
            border: 1px solid rgba(96, 165, 250, 0.45);
            background: rgba(59, 130, 246, 0.16);
        }

        .fg-sidebar-badge-engine {
            color: #99f6e4 !important;
            border: 1px solid rgba(45, 212, 191, 0.4);
            background: rgba(20, 184, 166, 0.14);
        }

        .fg-sidebar-engine-status {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            margin-top: 0.9rem;
            color: #a7f3d0 !important;
            font-size: 0.72rem;
        }

        .fg-sidebar-engine-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #34d399;
        }

        /* Desktop column balance */
        div[data-testid="stColumn"] {
            padding: 0 0.45rem !important;
        }

        @media (max-width: 1300px) {
            div[data-testid="stHorizontalBlock"]:has(.fg-kpi-container) > div[data-testid="stColumn"] {
                flex: 1 1 calc(50% - 16px) !important;
                min-width: calc(50% - 16px) !important;
            }
        }

        @media (max-width: 1000px) {
            div[data-testid="stHorizontalBlock"]:has(.fg-card) > div[data-testid="stColumn"] {
                flex: 1 1 100% !important;
                min-width: 100% !important;
            }
        }

        /* Desktop custom scrollbar */
        ::-webkit-scrollbar {
            width: 7px;
            height: 7px;
        }
        ::-webkit-scrollbar-track {
            background: #f1f5f9;
        }
        ::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
        }

        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label {
            color: #94a3b8 !important;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #f8fafc !important;
        }

        section[data-testid="stSidebar"] .stRadio label {
            color: #cbd5e1 !important;
        }

        /* Readable interactive controls and financial tables */
        input, textarea, [data-baseweb="select"] > div {
            border-radius: 9px !important;
        }

        div[data-testid="stDataFrame"] {
            background: #ffffff !important;
        }

        div[data-testid="stDataFrame"] [role="columnheader"] {
            background: #f1f5f9 !important;
            color: #253858 !important;
            font-weight: 700 !important;
        }

        div[data-testid="stMetric"] {
            padding: 0.8rem 0.9rem;
            border: 1px solid var(--border-neutral);
            border-radius: 12px;
            background: #ffffff;
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--border-neutral) !important;
            border-radius: 11px !important;
            background: rgba(255,255,255,0.8);
        }

        /* Custom header pill */
        .fg-header-pill {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #1d4ed8;
            background-color: #eff6ff;
            border: 1px solid #bfdbfe;
            padding: 0.2rem 0.55rem;
            border-radius: 4px;
            margin-bottom: 0.5rem;
        }

        /* Divider enhancement */
        hr {
            margin: 1.5rem 0 !important;
            border-color: var(--border-neutral) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
