import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from app.database.repositories.validation_repository import ValidationRecord

logger = logging.getLogger("filingguard.validation.operating_income")

RULE_ID = "operating_income_presentation"
RULE_NAME = "Operating Income Presentation (Gross Profit - Operating Expenses)"
RULE_VERSION = "1.0.0"
CATEGORY = "income_statement"


def validate_operating_income(
    accession_number: str,
    cik: str,
    reported_operating_income: Optional[float],
    reported_gross_profit: Optional[float],
    reported_operating_expenses: Optional[float],
    relative_tolerance: float = 0.001,
    absolute_tolerance: float = 100000.0,
    confidence_scores: Optional[Dict[str, Any]] = None,
    evidence_refs: Optional[Dict[str, Any]] = None,
    component_breakdown: Optional[Dict[str, float]] = None,
) -> ValidationRecord:
    """Validate that Operating Income = Gross Profit - Operating Expenses where traceable facts exist.

    Important constraints:
    - Operating expenses must be traceable to real SEC filing facts (not imputed or invented).
    - If Gross Profit or Operating Expenses are not disclosed (e.g. single-step presentation),
      returns NOT_EVALUATED without error.
    - VAL-01: component_breakdown is included when operating expenses were aggregated
      from component facts rather than a single consolidated disclosure.
    """
    input_metrics = {
        "operating_income": reported_operating_income,
        "gross_profit": reported_gross_profit,
        "operating_expenses": reported_operating_expenses,
    }
    evidence_references = evidence_refs or {}

    # Check for missing components
    if reported_operating_income is None:
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=RULE_ID,
            rule_name=RULE_NAME,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=None,
            actual_value=None,
            configured_tolerance=absolute_tolerance,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation="Operating income validation skipped: Operating Income was not reported or extracted.",
            failure_reason="Missing Operating Income metric",
            recommendation="Confirm whether operating income is separately reported or combined with ordinary profit.",
        )

    if reported_gross_profit is None or reported_operating_expenses is None:
        missing_parts = []
        if reported_gross_profit is None:
            missing_parts.append("Gross Profit")
        if reported_operating_expenses is None:
            missing_parts.append("traceable Operating Expenses")

        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=RULE_ID,
            rule_name=RULE_NAME,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=None,
            actual_value=reported_operating_income,
            configured_tolerance=absolute_tolerance,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=(
                f"Operating income presentation could not be evaluated: {', '.join(missing_parts)} "
                "not disclosed as traceable filing facts (common in single-step income statement presentations)."
            ),
            failure_reason=f"Unavailable disclosure components: {', '.join(missing_parts)}",
            recommendation="Review income statement structure: determine if company presents a single-step format omitting gross profit or aggregates expenses differently.",
        )

    # Precision-safe calculation using Decimal
    d_op_inc = Decimal(str(reported_operating_income))
    d_gp = Decimal(str(reported_gross_profit))
    d_opex = Decimal(str(reported_operating_expenses))

    d_expected = d_gp - d_opex
    d_diff = abs(d_op_inc - d_expected)

    d_rel_diff = (d_diff / abs(d_op_inc)) if d_op_inc != Decimal("0") else Decimal("0")

    d_rel_tol = Decimal(str(relative_tolerance))
    d_abs_tol = Decimal(str(absolute_tolerance))
    d_tolerance = max(d_abs_tol, d_rel_tol * abs(d_op_inc))

    is_pass = d_diff <= d_tolerance

    # Component aggregation notation for explanations
    opex_source_note = ""
    if component_breakdown and "consolidated" not in component_breakdown:
        comp_names = list(component_breakdown.keys())
        opex_source_note = f" [OpEx aggregated from {len(comp_names)} component(s): {', '.join(comp_names)}]"

    # Confidence check
    confidence_warning = ""
    if confidence_scores:
        low_conf = [
            m for m in ["operating_income", "gross_profit"]
            if m in confidence_scores and getattr(confidence_scores[m], "confidence_score", 1.0) < 0.85
        ]
        if low_conf:
            confidence_warning = f" Notice: Input metrics ({', '.join(low_conf)}) have reduced confidence scores."

    status = "PASS" if is_pass else "FAIL"

    if is_pass:
        if d_diff == Decimal("0"):
            explanation = (
                f"Operating income presentation holds exactly: Operating Income (${float(d_op_inc):,.2f}) = "
                f"Gross Profit (${float(d_gp):,.2f}) - Operating Expenses (${float(d_opex):,.2f}) with zero difference."
                f"{opex_source_note}{confidence_warning}"
            )
        else:
            explanation = (
                f"Operating income presentation holds within tolerance: Operating Income (${float(d_op_inc):,.2f}) vs "
                f"Gross Profit - Operating Expenses (${float(d_expected):,.2f}). Difference of ${float(d_diff):,.2f} "
                f"({float(d_rel_diff)*100:.3f}%) is within tolerance ${float(d_tolerance):,.2f}."
                f"{opex_source_note}{confidence_warning}"
            )
        failure_reason = None
        recommendation = "Operating income relationship verified against traceable gross profit and operating expense disclosures."
    else:
        explanation = (
            f"Operating income mismatch: Operating Income (${float(d_op_inc):,.2f}) differs from "
            f"Gross Profit - Operating Expenses (${float(d_expected):,.2f}) by ${float(d_diff):,.2f} "
            f"({float(d_rel_diff)*100:.3f}%), exceeding allowable tolerance of ${float(d_tolerance):,.2f}."
            f"{opex_source_note}{confidence_warning}"
        )
        failure_reason = f"Operating income presentation discrepancy (${float(d_diff):,.2f} > ${float(d_tolerance):,.2f})"
        recommendation = (
            "Auditor review required: check whether operating expenses include restructuring charges, "
            "R&D capitalization, or other non-operating presentation lines."
        )

    return ValidationRecord(
        accession_number=accession_number,
        cik=cik,
        rule_id=RULE_ID,
        rule_name=RULE_NAME,
        rule_version=RULE_VERSION,
        validation_category=CATEGORY,
        status=status,
        expected_value=float(d_expected),
        actual_value=float(d_op_inc),
        absolute_difference=float(d_diff),
        relative_difference=float(d_rel_diff),
        configured_tolerance=float(d_tolerance),
        input_metrics=input_metrics,
        evidence_references=evidence_references,
        explanation=explanation,
        failure_reason=failure_reason,
        recommendation=recommendation,
    )

