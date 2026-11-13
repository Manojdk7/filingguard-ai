import pytest
from app.database.repositories.validation_repository import ValidationRecord, ValidationRepository
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact
from app.validation.accounting_equation import validate_accounting_equation
from app.validation.cross_statement import validate_cross_statement_metric
from app.validation.operating_income import validate_operating_income
from app.validation.yoy_analysis import validate_yoy_variance
from app.validation.engine import FinancialValidationEngine


def test_accounting_equation_exact_match():
    """Test 1: Accounting equation exact match (Assets = Liabilities + Equity) produces PASS with 0 diff."""
    res = validate_accounting_equation(
        accession_number="test-accn",
        cik="0000320193",
        reported_assets=400000000000.0,
        reported_liabilities=280000000000.0,
        reported_equity=120000000000.0,
    )
    assert res.status == "PASS"
    assert res.absolute_difference == 0.0
    assert res.relative_difference == 0.0
    assert "zero difference" in res.explanation


def test_accounting_equation_within_tolerance():
    """Test 2: Accounting equation within allowable rounding tolerance produces PASS."""
    res = validate_accounting_equation(
        accession_number="test-accn",
        cik="0000320193",
        reported_assets=400000000000.0,
        reported_liabilities=280000000000.0,
        reported_equity=120000500000.0,  # $500k rounding difference
        relative_tolerance=0.005,
        absolute_tolerance=1000000.0,
    )
    assert res.status == "PASS"
    assert res.absolute_difference == 500000.0
    assert "within tolerance" in res.explanation


def test_accounting_equation_outside_tolerance():
    """Test 3: Accounting equation outside tolerance produces FAIL with failure reason."""
    res = validate_accounting_equation(
        accession_number="test-accn",
        cik="0000320193",
        reported_assets=400000000000.0,
        reported_liabilities=250000000000.0,
        reported_equity=120000000000.0,  # $30B discrepancy
        relative_tolerance=0.005,
        absolute_tolerance=1000000.0,
    )
    assert res.status == "FAIL"
    assert res.absolute_difference == 30000000000.0
    assert "exceeding allowable tolerance" in res.explanation
    assert res.failure_reason is not None


def test_missing_equity_or_liabilities_not_evaluated():
    """Test 4: Missing liabilities or equity returns NOT_EVALUATED and does not treat missing as zero."""
    res = validate_accounting_equation(
        accession_number="test-accn",
        cik="0000320193",
        reported_assets=400000000000.0,
        reported_liabilities=None,
        reported_equity=120000000000.0,
    )
    assert res.status == "NOT_EVALUATED"
    assert "missing" in res.explanation
    assert res.expected_value is None


def test_operating_income_exact_match():
    """Test 5: Operating income exact match (Gross Profit - Operating Expenses)."""
    res = validate_operating_income(
        accession_number="test-accn",
        cik="0000320193",
        reported_operating_income=150000000000.0,
        reported_gross_profit=220000000000.0,
        reported_operating_expenses=70000000000.0,
    )
    assert res.status == "PASS"
    assert res.absolute_difference == 0.0


def test_operating_expenses_unavailable_not_evaluated():
    """Test 6: Operating expenses unavailable (single-step presentation) returns NOT_EVALUATED."""
    res = validate_operating_income(
        accession_number="test-accn",
        cik="0001018724",  # Amazon-like
        reported_operating_income=30000000000.0,
        reported_gross_profit=None,
        reported_operating_expenses=None,
    )
    assert res.status == "NOT_EVALUATED"
    assert "single-step" in res.explanation


def test_operating_income_mismatch():
    """Test 7: Operating income mismatch outside tolerance produces FAIL."""
    res = validate_operating_income(
        accession_number="test-accn",
        cik="0000320193",
        reported_operating_income=150000000000.0,
        reported_gross_profit=220000000000.0,
        reported_operating_expenses=60000000000.0,  # Diff of $10B
    )
    assert res.status == "FAIL"
    assert res.absolute_difference == 10000000000.0
    assert "mismatch" in res.explanation


def test_positive_yoy_growth():
    """Test 8: Normal positive YoY growth within threshold produces PASS."""
    res = validate_yoy_variance(
        accession_number="test-accn",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        current_value=120000000.0,
        prior_value=100000000.0,
        warning_threshold_pct=40.0,
    )
    assert res.status == "PASS"
    assert res.absolute_difference == 20000000.0
    assert round(res.relative_difference * 100.0, 2) == 20.0


def test_negative_yoy_growth_anomaly():
    """Test 9: Negative YoY variance exceeding threshold produces WARNING (not fraud)."""
    res = validate_yoy_variance(
        accession_number="test-accn",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        current_value=50000000.0,
        prior_value=100000000.0,  # -50% decline
        warning_threshold_pct=40.0,
    )
    assert res.status == "WARNING"
    assert res.absolute_difference == -50000000.0
    assert round(res.relative_difference * 100.0, 2) == -50.0
    assert "not proof of error or misconduct" in res.explanation


def test_previous_year_value_zero():
    """Test 10: Previous year value is zero handles division by zero safely and produces WARNING."""
    res = validate_yoy_variance(
        accession_number="test-accn",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        current_value=50000000.0,
        prior_value=0.0,
    )
    assert res.status == "WARNING"
    assert res.relative_difference is None
    assert "division by zero" in res.explanation


def test_negative_financial_values_yoy():
    """Test 11: Negative financial values (e.g. net loss to profit) properly preserved in YoY."""
    # Prior: -100M loss, Current: +50M profit -> growth is +150M / |-100M| = +150%
    res = validate_yoy_variance(
        accession_number="test-accn",
        cik="0000320193",
        metric_id="net_income",
        canonical_name="Net Income",
        current_value=50000000.0,
        prior_value=-100000000.0,
        warning_threshold_pct=40.0,
    )
    assert res.status == "WARNING"
    assert res.absolute_difference == 150000000.0
    assert round(res.relative_difference * 100.0, 2) == 150.0


def test_missing_prior_year_facts():
    """Test 12: Missing prior year fact returns NOT_EVALUATED."""
    res = validate_yoy_variance(
        accession_number="test-accn",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        current_value=100000000.0,
        prior_value=None,
    )
    assert res.status == "NOT_EVALUATED"


def test_unit_mismatch_yoy():
    """Test 14: Unit mismatch between comparative periods returns NOT_EVALUATED."""
    res = validate_yoy_variance(
        accession_number="test-accn",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        current_value=100000000.0,
        prior_value=100000000.0,
        current_unit="USD",
        prior_unit="shares",
    )
    assert res.status == "NOT_EVALUATED"
    assert "unit mismatch" in res.explanation


def test_cross_statement_exact_match():
    """Test 15: Cross-statement exact match produces PASS."""
    res = validate_cross_statement_metric(
        accession_number="test-accn",
        cik="0000320193",
        rule_id="cross_statement_net_income",
        rule_name="Net Income Cross-Statement",
        source_statement="Income Statement",
        target_statement="Cash Flow Statement",
        source_value=132175000000.0,
        target_value=132175000000.0,
        tolerance=1.0,
    )
    assert res.status == "PASS"
    assert res.absolute_difference == 0.0


def test_cross_statement_mismatch():
    """Test 16: Cross-statement discrepancy produces FAIL."""
    res = validate_cross_statement_metric(
        accession_number="test-accn",
        cik="0000320193",
        rule_id="cross_statement_net_income",
        rule_name="Net Income Cross-Statement",
        source_statement="Income Statement",
        target_statement="Cash Flow Statement",
        source_value=132175000000.0,
        target_value=130000000000.0,
        tolerance=1.0,
    )
    assert res.status == "FAIL"
    assert res.absolute_difference == 2175000000.0


def test_low_confidence_input_facts_flagged():
    """Test 17: Validations with low-confidence inputs include warning in explanation."""
    class MockConf:
        confidence_score = 0.55

    res = validate_accounting_equation(
        accession_number="test-accn",
        cik="0000320193",
        reported_assets=400000000000.0,
        reported_liabilities=280000000000.0,
        reported_equity=120000000000.0,
        confidence_scores={"total_assets": MockConf()},
    )
    assert res.status == "PASS"
    assert "reduced confidence" in res.explanation


def test_rule_versioning():
    """Test 20: Every validation record includes rule_version."""
    res = validate_accounting_equation(
        accession_number="test-accn",
        cik="0000320193",
        reported_assets=400000000000.0,
        reported_liabilities=280000000000.0,
        reported_equity=120000000000.0,
    )
    assert res.rule_version == "1.0.0"


def test_idempotent_persistence():
    """Test 21: Repeated validation persistence replaces records without duplicates."""
    repo = ValidationRepository()
    accn = "test-val-idempotent-001"

    rec = ValidationRecord(
        accession_number=accn,
        cik="0000320193",
        rule_id="balance_sheet_equation",
        rule_name="Accounting Equation",
        rule_version="1.0.0",
        validation_category="balance_sheet",
        status="PASS",
        expected_value=400000000000.0,
        actual_value=400000000000.0,
        absolute_difference=0.0,
        relative_difference=0.0,
        configured_tolerance=1000000.0,
        input_metrics={"assets": 400000000000.0},
        evidence_references={},
        explanation="Holds exactly",
    )

    # Save once
    repo.save_validations([rec])
    # Save twice
    repo.save_validations([rec])

    records = repo.get_validations_by_accession(accn)
    assert len(records) == 1
    assert records[0].status == "PASS"



# ===========================================================================
# VAL-01: Operating Expense Aggregation Tests
# ===========================================================================

def _make_xbrl_fact(concept_name, numeric_value, end_date="2026-09-26",
                    period_type="duration", is_segment=False, context_id="c1",
                    source_locator=None, start_date=None):
    """Helper to create a ParsedXBRLFact for testing."""
    return ParsedXBRLFact(
        accession_number="test-accn",
        concept_name=concept_name,
        namespace="us-gaap",
        value=str(numeric_value),
        numeric_value=numeric_value,
        unit="USD",
        context_id=context_id,
        period_type=period_type,
        start_date=start_date or "2025-09-27",
        end_date=end_date,
        is_segment=is_segment,
        source_locator=source_locator,
    )


def test_opex_aggregation_prefers_consolidated():
    """VAL-01 Test: When a consolidated OperatingExpenses fact exists, use it directly."""
    xbrl_facts = [
        _make_xbrl_fact("OperatingExpenses", 70000000000.0),
        _make_xbrl_fact("ResearchAndDevelopmentExpense", 30000000000.0),
        _make_xbrl_fact("SellingGeneralAndAdministrativeExpense", 40000000000.0),
    ]
    total, breakdown, evidence = FinancialValidationEngine._aggregate_operating_expenses(
        xbrl_facts, "2026-09-26"
    )
    assert total == 70000000000.0
    assert breakdown == {"consolidated": 70000000000.0}
    assert evidence["source"] == "consolidated"


def test_opex_aggregation_component_fallback():
    """VAL-01 Test: When no consolidated fact exists, aggregate component facts."""
    xbrl_facts = [
        _make_xbrl_fact("ResearchAndDevelopmentExpense", 30000000000.0),
        _make_xbrl_fact("SellingGeneralAndAdministrativeExpense", 40000000000.0),
    ]
    total, breakdown, evidence = FinancialValidationEngine._aggregate_operating_expenses(
        xbrl_facts, "2026-09-26"
    )
    assert total == 70000000000.0
    assert "ResearchAndDevelopmentExpense" in breakdown
    assert "SellingGeneralAndAdministrativeExpense" in breakdown
    assert evidence["source"] == "component_aggregation"


def test_opex_aggregation_prevents_sga_double_counting():
    """VAL-01 Test: When SG&A is present, its sub-components are excluded."""
    xbrl_facts = [
        _make_xbrl_fact("ResearchAndDevelopmentExpense", 30000000000.0),
        _make_xbrl_fact("SellingGeneralAndAdministrativeExpense", 40000000000.0),
        _make_xbrl_fact("SellingAndMarketingExpense", 15000000000.0),  # should be excluded
        _make_xbrl_fact("GeneralAndAdministrativeExpense", 25000000000.0),  # should be excluded
    ]
    total, breakdown, evidence = FinancialValidationEngine._aggregate_operating_expenses(
        xbrl_facts, "2026-09-26"
    )
    assert total == 70000000000.0
    assert "SellingAndMarketingExpense" not in breakdown
    assert "GeneralAndAdministrativeExpense" not in breakdown


def test_opex_aggregation_excludes_tax_and_interest():
    """VAL-01 Test: Tax and interest expense facts are excluded from aggregation."""
    xbrl_facts = [
        _make_xbrl_fact("ResearchAndDevelopmentExpense", 30000000000.0),
        _make_xbrl_fact("SellingGeneralAndAdministrativeExpense", 40000000000.0),
        _make_xbrl_fact("IncomeTaxExpenseBenefit", 15000000000.0),  # excluded
        _make_xbrl_fact("InterestExpense", 5000000000.0),  # excluded
    ]
    total, breakdown, evidence = FinancialValidationEngine._aggregate_operating_expenses(
        xbrl_facts, "2026-09-26"
    )
    assert total == 70000000000.0
    assert "IncomeTaxExpenseBenefit" not in breakdown
    assert "InterestExpense" not in breakdown


def test_opex_aggregation_requires_minimum_two_components():
    """VAL-01 Test: A single component is insufficient for aggregation."""
    xbrl_facts = [
        _make_xbrl_fact("ResearchAndDevelopmentExpense", 30000000000.0),
    ]
    total, breakdown, evidence = FinancialValidationEngine._aggregate_operating_expenses(
        xbrl_facts, "2026-09-26"
    )
    assert total is None
    assert breakdown is None


def test_opex_aggregation_ignores_segment_facts():
    """VAL-01 Test: Segment-level facts are excluded from aggregation."""
    xbrl_facts = [
        _make_xbrl_fact("ResearchAndDevelopmentExpense", 30000000000.0, is_segment=True),
        _make_xbrl_fact("SellingGeneralAndAdministrativeExpense", 40000000000.0, is_segment=True),
    ]
    total, breakdown, evidence = FinancialValidationEngine._aggregate_operating_expenses(
        xbrl_facts, "2026-09-26"
    )
    assert total is None


def test_operating_income_with_component_breakdown():
    """VAL-01 Test: validate_operating_income includes component breakdown in explanation."""
    res = validate_operating_income(
        accession_number="test-accn",
        cik="0000320193",
        reported_operating_income=150000000000.0,
        reported_gross_profit=220000000000.0,
        reported_operating_expenses=70000000000.0,
        component_breakdown={
            "ResearchAndDevelopmentExpense": 30000000000.0,
            "SellingGeneralAndAdministrativeExpense": 40000000000.0,
        },
    )
    assert res.status == "PASS"
    assert "aggregated from 2 component(s)" in res.explanation


# ===========================================================================
# VAL-02: Cross-Statement Net Income Independence Tests
# ===========================================================================

def test_cross_statement_same_fact_returns_not_evaluated():
    """VAL-02 Test: When the same fact is referenced for both statements, return NOT_EVALUATED."""
    res = validate_cross_statement_metric(
        accession_number="test-accn",
        cik="0000320193",
        rule_id="cross_statement_net_income",
        rule_name="Net Income Cross-Statement",
        source_statement="Income Statement",
        target_statement="Cash Flow Statement",
        source_value=132175000000.0,
        target_value=132175000000.0,
        tolerance=1.0,
        is_same_fact=True,
    )
    assert res.status == "NOT_EVALUATED"
    assert "insufficient independent cross-statement evidence" in res.explanation.lower()
    assert "same fact record" in res.failure_reason.lower()


def test_cross_statement_independent_facts_pass():
    """VAL-02 Test: Independent facts from different statements produce normal PASS/FAIL."""
    res = validate_cross_statement_metric(
        accession_number="test-accn",
        cik="0000320193",
        rule_id="cross_statement_net_income",
        rule_name="Net Income Cross-Statement",
        source_statement="Income Statement",
        target_statement="Cash Flow Statement",
        source_value=132175000000.0,
        target_value=132175000000.0,
        tolerance=1.0,
        is_same_fact=False,
    )
    assert res.status == "PASS"
    assert res.absolute_difference == 0.0


def test_cross_statement_independent_facts_fail():
    """VAL-02 Test: Independent facts that disagree produce FAIL."""
    res = validate_cross_statement_metric(
        accession_number="test-accn",
        cik="0000320193",
        rule_id="cross_statement_net_income",
        rule_name="Net Income Cross-Statement",
        source_statement="Income Statement",
        target_statement="Cash Flow Statement",
        source_value=132175000000.0,
        target_value=130000000000.0,
        tolerance=1.0,
        is_same_fact=False,
    )
    assert res.status == "FAIL"
    assert res.absolute_difference == 2175000000.0


def test_cross_statement_same_fact_false_by_default():
    """VAL-02 Test: is_same_fact defaults to False for backward compatibility."""
    res = validate_cross_statement_metric(
        accession_number="test-accn",
        cik="0000320193",
        rule_id="cross_statement_cash",
        rule_name="Cash Cross-Statement",
        source_statement="Balance Sheet",
        target_statement="Cash Flow Statement",
        source_value=36305000000.0,
        target_value=36305000000.0,
        tolerance=1.0,
    )
    assert res.status == "PASS"
