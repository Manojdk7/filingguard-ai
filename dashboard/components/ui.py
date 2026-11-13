"""
Reusable UI helper components for FilingGuard AI enterprise dashboard.
"""
from html import escape
from typing import Optional
import streamlit as st


def render_header(title: str, subtitle: str, category_chip: Optional[str] = None):
    """Render a standardized enterprise page header."""
    chip_html = (
        f'<div class="fg-header-pill">{escape(category_chip)}</div>'
        if category_chip
        else ""
    )
    st.markdown(
        f"""
        <section class="fg-page-header">
            {chip_html}
            <div class="fg-page-heading">
                <span class="fg-page-icon" aria-hidden="true">◈</span>
                <div>
                    <h1>{escape(title)}</h1>
                    <p>{escape(subtitle)}</p>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(
    label: str,
    value: str,
    subtext: Optional[str] = None,
    status: str = "neutral",
):
    """Render a styled metric KPI card.
    
    status can be: 'neutral', 'success', 'warning', 'danger', 'info'
    """
    status_class = f"fg-kpi-{status}" if status != "neutral" else ""
    subtext_html = (
        f'<div class="fg-kpi-subtext">{escape(subtext)}</div>' if subtext else ""
    )
    card_html = f"""
    <div class="fg-kpi-container {status_class}">
        <div class="fg-kpi-label">{escape(label)}</div>
        <div class="fg-kpi-value">{escape(value)}</div>
        {subtext_html}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def render_badge(text: str, status: str = "neutral") -> str:
    """Return HTML string for a colored status pill."""
    status_map = {
        "success": "fg-badge-success",
        "warning": "fg-badge-warning",
        "danger": "fg-badge-danger",
        "info": "fg-badge-info",
        "neutral": "fg-badge-neutral",
    }
    css_class = status_map.get(status, "fg-badge-neutral")
    return f'<span class="fg-badge {css_class}">{escape(text)}</span>'


def render_callout(message: str, status: str = "info", title: Optional[str] = None):
    """Render a styled alert callout box."""
    colors = {
        "success": ("#ecfdf5", "#a7f3d0", "#065f46", "🟢"),
        "warning": ("#fffbeb", "#fde68a", "#92400e", "⚠️"),
        "danger": ("#fef2f2", "#fecaca", "#991b1b", "🚨"),
        "info": ("#eff6ff", "#bfdbfe", "#1e40af", "ℹ️"),
    }
    bg, border, text_color, icon = colors.get(status, colors["info"])
    title_html = (
        f"<div style='font-weight: 700; margin-bottom: 0.25rem; color: {text_color};'>{icon} {escape(title)}</div>"
        if title
        else ""
    )
    st.markdown(
        f"""
        <div style="background-color: {bg}; border: 1px solid {border}; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem;">
            {title_html}
            <div style="color: {text_color}; font-size: 0.92rem; line-height: 1.5;">{escape(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_currency(value: Optional[float], compact: bool = False) -> str:
    """Format a monetary amount as human-readable USD."""
    if value is None:
        return "N/A"
    if compact:
        abs_v = abs(value)
        if abs_v >= 1e9:
            return f"${value / 1e9:,.2f}B"
        elif abs_v >= 1e6:
            return f"${value / 1e6:,.2f}M"
        elif abs_v >= 1e3:
            return f"${value / 1e3:,.1f}K"
        return f"${value:,.0f}"
    return f"${value:,.0f}"


def format_percentage(value: Optional[float], signed: bool = True) -> str:
    """Format a decimal ratio as percentage."""
    if value is None:
        return "N/A"
    pct = value * 100.0 if abs(value) <= 10.0 else value
    sign = "+" if signed and pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def render_sidebar_branding():
    """Render professional enterprise branding and navigation cues in the Streamlit sidebar."""
    with st.sidebar:
        st.markdown(
            """
            <div class="fg-sidebar-brand">
                <div class="fg-sidebar-brand-row">
                    <span class="fg-sidebar-logo">🛡️</span>
                    <div>
                        <div class="fg-sidebar-title">FilingGuard AI</div>
                        <div class="fg-sidebar-subtitle">SEC Audit Engine</div>
                    </div>
                </div>
                <div class="fg-sidebar-badges">
                    <span class="fg-sidebar-badge fg-sidebar-badge-version">v0.1.0</span>
                    <span class="fg-sidebar-badge fg-sidebar-badge-engine">Deterministic</span>
                </div>
                <div class="fg-sidebar-engine-status">
                    <span class="fg-sidebar-engine-dot"></span>
                    Audit engine ready
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
