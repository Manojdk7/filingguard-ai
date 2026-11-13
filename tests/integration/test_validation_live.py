import pytest
from app.validation.engine import FinancialValidationEngine
from app.database.repositories.validation_repository import ValidationRepository


def test_live_apple_financial_validation():
    """Integration test: validate real Apple Inc. 10-K filing from cached database records and iXBRL facts."""
    accession_number = "0000320193-26-000026"
    engine = FinancialValidationEngine()

    results = engine.validate_filing(accession_number)
    assert len(results) >= 12  # Equation, Operating Income, 10 YoY checks, 2 Cross-statement

    results_by_rule = {r.rule_id: r for r in results}

    # 1. Accounting equation check
    eq = results_by_rule.get("balance_sheet_equation")
    assert eq is not None
    assert eq.status == "PASS"
    assert eq.actual_value == 404548000000.0  # Total Assets
    assert eq.expected_value == 404548000000.0  # Liabilities + Equity
    assert eq.absolute_difference == 0.0  # Exact dollar match!

    # 2. Operating income check
    op = results_by_rule.get("operating_income_presentation")
    assert op is not None
    assert op.status == "PASS"
    assert op.actual_value == 158063000000.0  # Operating Income
    assert op.expected_value == 158063000000.0  # Gross Profit - Operating Expenses
    assert op.absolute_difference == 0.0  # Exact dollar match!

    # 3. YoY variance checks
    yoy_rev = results_by_rule.get("yoy_variance_revenue")
    assert yoy_rev is not None
    assert yoy_rev.status == "PASS"
    assert yoy_rev.actual_value == 478834000000.0
    assert yoy_rev.expected_value == 416161000000.0
    assert round(yoy_rev.relative_difference * 100.0, 2) == 15.06  # 15.06% revenue growth

    # 4. Cross-statement checks
    cs_ni = results_by_rule.get("cross_statement_net_income")
    assert cs_ni is not None
    assert cs_ni.status == "PASS"
    assert cs_ni.actual_value == 132175000000.0
    assert cs_ni.expected_value == 132175000000.0

    # 5. Database persistence verification
    val_repo = ValidationRepository()
    saved = val_repo.get_validations_by_accession(accession_number)
    assert len(saved) == len(results)

    summary = val_repo.get_validation_summary(accession_number)
    assert summary["failed"] == 0
    assert summary["passed"] >= 10

