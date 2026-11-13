import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from app.database.repositories.validation_repository import ValidationRecord

logger = logging.getLogger("filingguard.validation.cross_statement")

RULE_VERSION = "1.0.0"
CATEGORY = "cross_statement"


def validate_cross_statement_metric(
    accession_number: str,
    cik: str,
    rule_id: str,
    rule_name: str,
    source_statement: str,
    target_statement: str,
    source_value: Optional[float],
    target_value: Optional[float],
    tolerance: float = 1.0,
    source_period: Optional[str] = None,
    target_period: Optional[str] = None,
    source_unit: str = "USD",
    target_unit: str = "USD",
    confidence_scores: Optional[Dict[str, Any]] = None,
    evidence_refs: Optional[Dict[str, Any]] = None,
    is_same_fact: bool = False,
) -> ValidationRecord:
    """Validate cross-statement consistency between identical financial concepts appearing in different statements.

    Examples:
    - Net Income: Income Statement vs. Cash Flow Statement operating reconciliation.
    - Cash & Cash Equivalents: Balance Sheet vs. Statement of Cash Flows ending balance.

    VAL-02: When is_same_fact=True, the same underlying fact record was referenced
    for both statements. This produces NOT_EVALUATED instead of a misleading PASS.
    """
    input_metrics = {
        "source_statement": source_statement,
        "target_statement": target_statement,
        "source_value": source_value,
        "target_value": target_value,
        "source_period": source_period,
        "target_period": target_period,
        "source_unit": source_unit,
        "target_unit": target_unit,
    }
    evidence_references = evidence_refs or {}

    # VAL-02: If same fact is being compared to itself, return NOT_EVALUATED
    if is_same_fact and source_value is not None and target_value is not None:
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=source_value,
            actual_value=target_value,
            configured_tolerance=tolerance,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=(
                f"Cross-statement validation not evaluated: insufficient independent cross-statement evidence. "
                f"The same fact record was referenced for both {source_statement} and {target_statement}. "
                f"A genuine cross-statement check requires independently presented facts from different financial statements."
            ),
            failure_reason="Insufficient independent cross-statement evidence: same fact record referenced for both statements",
            recommendation=(
                "Verify that the filing includes independently tagged Net Income facts on both "
                "the Income Statement and the Cash Flow Statement with distinct context identifiers."
            ),
        )

    # Check for missing values
    if source_value is None or target_value is None:
        missing = source_statement if source_value is None else target_statement
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=source_value,
            actual_value=target_value,
            configured_tolerance=tolerance,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=f"Cross-statement consistency could not be evaluated: fact from {missing} is not available.",
            failure_reason=f"Missing {missing} disclosure",
            recommendation="Confirm whether the metric is separately presented in both statements.",
        )

    # Check unit compatibility
    if source_unit.upper() != target_unit.upper():
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=source_value,
            actual_value=target_value,
            configured_tolerance=tolerance,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=f"Cross-statement validation aborted due to unit incompatibility: {source_unit} vs {target_unit}.",
            failure_reason="Unit incompatibility",
            recommendation="Verify reporting units across primary statement tables.",
        )

    # Precision-safe comparison using Decimal
    d_source = Decimal(str(source_value))
    d_target = Decimal(str(target_value))
    d_diff = abs(d_source - d_target)
    d_tol = Decimal(str(tolerance))

    is_pass = d_diff <= d_tol
    status = "PASS" if is_pass else "FAIL"

    if is_pass:
        explanation = (
            f"Cross-statement consistency verified: {source_statement} (${float(d_source):,.2f}) matches "
            f"{target_statement} (${float(d_target):,.2f}) with diff of ${float(d_diff):,.2f} within tolerance ${float(d_tol):,.2f}."
        )
        failure_reason = None
        recommendation = "Cross-statement disclosures are consistent."
    else:
        explanation = (
            f"Cross-statement mismatch detected: {source_statement} (${float(d_source):,.2f}) differs from "
            f"{target_statement} (${float(d_target):,.2f}) by ${float(d_diff):,.2f}, exceeding allowable tolerance of ${float(d_tol):,.2f}."
        )
        failure_reason = f"Cross-statement difference (${float(d_diff):,.2f} > ${float(d_tol):,.2f})"
        recommendation = "Inspect statement line footnotes for restricted cash definitions, noncontrolling interest, or discontinued operations."

    return ValidationRecord(
        accession_number=accession_number,
        cik=cik,
        rule_id=rule_id,
        rule_name=rule_name,
        rule_version=RULE_VERSION,
        validation_category=CATEGORY,
        status=status,
        expected_value=float(d_source),
        actual_value=float(d_target),
        absolute_difference=float(d_diff),
        relative_difference=float(d_diff / abs(d_source)) if d_source != Decimal("0") else 0.0,
        configured_tolerance=float(d_tol),
        input_metrics=input_metrics,
        evidence_references=evidence_references,
        explanation=explanation,
        failure_reason=failure_reason,
        recommendation=recommendation,
    )

