import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.database.repositories.validation_repository import ValidationRecord

logger = logging.getLogger("filingguard.validation.yoy_analysis")

RULE_ID_PREFIX = "yoy_variance_"
RULE_VERSION = "1.0.0"
CATEGORY = "variance"


def validate_yoy_variance(
    accession_number: str,
    cik: str,
    metric_id: str,
    canonical_name: str,
    current_value: Optional[float],
    prior_value: Optional[float],
    warning_threshold_pct: float = 40.0,
    current_period: Optional[str] = None,
    prior_period: Optional[str] = None,
    current_unit: str = "USD",
    prior_unit: str = "USD",
    confidence_scores: Optional[Dict[str, Any]] = None,
    evidence_refs: Optional[Dict[str, Any]] = None,
) -> ValidationRecord:
    """Calculate Year-over-Year (YoY) percentage and absolute change for a metric.

    Formula:
        YoY Change (%) = ((current_value - prior_value) / abs(prior_value)) * 100

    Edge Cases:
    - Missing prior-year value: returns NOT_EVALUATED.
    - Prior value == 0: percentage change mathematically undefined; returns absolute change and WARNING.
    - Negative values: preserves directional growth using abs(prior_value) denominator.
    - Variances > threshold: flags as WARNING (material anomaly), never labelled fraud.
    """
    rule_id = f"{RULE_ID_PREFIX}{metric_id}"
    rule_name = f"YoY Variance: {canonical_name}"
    input_metrics = {
        "metric_id": metric_id,
        "canonical_name": canonical_name,
        "current_value": current_value,
        "prior_value": prior_value,
        "current_period": current_period,
        "prior_period": prior_period,
        "current_unit": current_unit,
        "prior_unit": prior_unit,
    }
    evidence_references = evidence_refs or {}

    # Check for missing values
    if current_value is None or prior_value is None:
        missing = "current value" if current_value is None else "prior-year comparative value"
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=prior_value,
            actual_value=current_value,
            configured_tolerance=warning_threshold_pct,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=f"YoY variance could not be evaluated for {canonical_name}: {missing} is not available in filing disclosures.",
            failure_reason=f"Missing {missing}",
            recommendation="Confirm whether previous fiscal year financial statements are disclosed under comparative columns.",
        )

    # Unit compatibility check
    if current_unit.upper() != prior_unit.upper():
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=prior_value,
            actual_value=current_value,
            configured_tolerance=warning_threshold_pct,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=f"YoY variance aborted for {canonical_name}: unit mismatch ({current_unit} vs {prior_unit}).",
            failure_reason="Unit incompatibility",
            recommendation="Normalize units to standard currency before comparative variance analysis.",
        )

    # Precision-safe calculation
    d_curr = Decimal(str(current_value))
    d_prior = Decimal(str(prior_value))
    d_abs_diff = d_curr - d_prior

    # Edge case: Prior value is zero
    if d_prior == Decimal("0"):
        explanation = (
            f"YoY variance for {canonical_name}: prior-year value was $0.00. Absolute change is "
            f"${float(d_abs_diff):,.2f}. Percentage change is mathematically undefined (division by zero)."
        )
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="WARNING",
            expected_value=0.0,
            actual_value=float(d_curr),
            absolute_difference=float(d_abs_diff),
            relative_difference=None,
            configured_tolerance=warning_threshold_pct,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=explanation,
            failure_reason="Prior year value is zero (base effect)",
            recommendation="Review disclosure notes to determine if business line was newly formed or acquired.",
        )

    d_rel_change = (d_abs_diff / abs(d_prior)) * Decimal("100")
    pct_change = float(d_rel_change)
    abs_change = float(d_abs_diff)

    is_anomaly = abs(pct_change) > warning_threshold_pct

    status = "WARNING" if is_anomaly else "PASS"

    direction = "increase" if pct_change >= 0 else "decrease"
    if is_anomaly:
        explanation = (
            f"Material YoY variance detected for {canonical_name}: {direction} of {abs(pct_change):.2f}% "
            f"(${abs_change:,.2f}), exceeding anomaly threshold of {warning_threshold_pct:.1f}%. "
            "(Note: Anomaly flag indicates substantial business change, not proof of error or misconduct)."
        )
        failure_reason = f"YoY variance of {pct_change:.2f}% exceeds {warning_threshold_pct:.1f}% threshold"
        recommendation = "Review MD&A (Management's Discussion and Analysis) to corroborate operational drivers of change."
    else:
        explanation = (
            f"Normal YoY variance for {canonical_name}: {direction} of {abs(pct_change):.2f}% "
            f"(${abs_change:,.2f}) is within {warning_threshold_pct:.1f}% threshold."
        )
        failure_reason = None
        recommendation = "YoY variance is within normal operational bounds."

    return ValidationRecord(
        accession_number=accession_number,
        cik=cik,
        rule_id=rule_id,
        rule_name=rule_name,
        rule_version=RULE_VERSION,
        validation_category=CATEGORY,
        status=status,
        expected_value=float(d_prior),
        actual_value=float(d_curr),
        absolute_difference=abs_change,
        relative_difference=pct_change / 100.0,
        configured_tolerance=warning_threshold_pct,
        input_metrics=input_metrics,
        evidence_references=evidence_references,
        explanation=explanation,
        failure_reason=failure_reason,
        recommendation=recommendation,
    )

