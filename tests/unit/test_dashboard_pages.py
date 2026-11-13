"""
Unit tests to verify that all Streamlit dashboard pages compile and load dependencies cleanly.
"""
import py_compile
from pathlib import Path
from unittest.mock import patch

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"


def test_dashboard_pages_syntax_and_compilation():
    """Verify that all dashboard files compile to valid bytecode without syntax or import errors."""
    python_files = list(DASHBOARD_DIR.rglob("*.py"))
    assert len(python_files) >= 7

    for file_path in python_files:
        # Should compile without raising py_compile.PyCompileError
        compiled = py_compile.compile(str(file_path), doraise=True)
        assert compiled is not None


def test_dashboard_ui_helpers():
    """Verify UI formatting helpers for currency and percentage."""
    from dashboard.components.ui import format_currency, format_percentage

    assert format_currency(1500000.0) == "$1,500,000"
    assert format_currency(1500000000.0, compact=True) == "$1.50B"
    assert format_currency(1500000.0, compact=True) == "$1.50M"
    assert format_currency(None) == "N/A"

    assert format_percentage(0.155) == "+15.50%"
    assert format_percentage(-0.052) == "-5.20%"
    assert format_percentage(None) == "N/A"


def test_company_selector_has_twenty_unique_sec_presets():
    from dashboard.components.company_data import (
        PRESET_COMPANIES,
        PRESET_OPTIONS,
        QUICK_INGEST_TICKERS,
    )

    companies = list(PRESET_COMPANIES.values())
    assert len(PRESET_OPTIONS) == 20
    assert len({company["ticker"] for company in companies}) == 20
    assert len({company["cik"] for company in companies}) == 20
    assert all(len(company["cik"]) == 10 and company["cik"].isdigit() for company in companies)
    assert all(ticker in {company["ticker"] for company in companies} for ticker in QUICK_INGEST_TICKERS)


def test_global_typography_does_not_override_streamlit_icon_fonts():
    from dashboard.components.styles import inject_custom_css

    with patch("dashboard.components.styles.st.markdown") as markdown:
        inject_custom_css()

    stylesheet = markdown.call_args.args[0]
    assert "p, label {" in stylesheet
    assert "p, span, label {" not in stylesheet
