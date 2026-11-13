import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.database.repositories.validation_repository import ValidationRecord

logger = logging.getLogger("filingguard.validation.accounting_equation")

RULE_ID = "balance_sheet_equation"
RULE_NAME = "Accounting Equation (Assets = Liabilities + Equity)"
RULE_VERSION = "1.0.0"
CATEGORY = "balance_sheet"


def validate_accounting_equation(
    accession_number: str,
    cik: str,
    reported_assets: Optional[float],
    reported_liabilities: Optional[float],
    reported_equity: Optional[float],
    relative_tolerance: float = 0.005,
    absolute_tolerance: float = 1000000.0,
    confidence_scores: Optional[Dict[str, Any]] = None,
    evidence_refs: Optional[Dict[str, Any]] = None,
) -> ValidationRecord:
    """Validate that Total Assets = Total Liabilities + Stockholders' Equity.

    Formula:
        Assets ≈ Liabilities + Equity
        tolerance = max(absolute_tolerance, relative_tolerance * abs(assets))
    """
    input_metrics = {
        "total_assets": reported_assets,
        "total_liabilities": reported_liabilities,
        "stockholders_equity": reported_equity,
    }
    evidence_references = evidence_refs or {}

    # Check for missing components - do NOT silently substitute zero
    missing = [k for k, v in input_metrics.items() if v is None]
    if missing:
        missing_names = ", ".join(missing)
        return ValidationRecord(
            accession_number=accession_number,
            cik=cik,
            rule_id=RULE_ID,
            rule_name=RULE_NAME,
            rule_version=RULE_VERSION,
            validation_category=CATEGORY,
            status="NOT_EVALUATED",
            expected_value=None,
            actual_value=reported_assets,
            absolute_difference=None,
            relative_difference=None,
            configured_tolerance=absolute_tolerance,
            input_metrics=input_metrics,
            evidence_references=evidence_references,
            explanation=f"Accounting equation could not be evaluated because required component(s) are missing: {missing_names}.",
            failure_reason=f"Missing disclosures: {missing_names}",
            recommendation="Inspect filing disclosures to determine if unaggregated liabilities or non-controlling equity are reported under non-standard concepts.",
        )

    # Precision-safe calculation using Decimal
    d_assets = Decimal(str(reported_assets))
    d_liabilities = Decimal(str(reported_liabilities))
    d_equity = Decimal(str(reported_equity))

    d_expected = d_liabilities + d_equity
    d_diff = abs(d_assets - d_expected)

    d_rel_diff = (d_diff / abs(d_assets)) if d_assets != Decimal("0") else Decimal("0")

    d_rel_tol = Decimal(str(relative_tolerance))
    d_abs_tol = Decimal(str(absolute_tolerance))
    d_tolerance = max(d_abs_tol, d_rel_tol * abs(d_assets))

    is_pass = d_diff <= d_tolerance

    # Check if inputs have low confidence
    confidence_warning = ""
    if confidence_scores:
        low_conf = [
            m for m in ["total_assets", "total_liabilities", "stockholders_equity"]
            if m in confidence_scores and getattr(confidence_scores[m], "confidence_score", 1.0) < 0.85
        ]
        if low_conf:
            confidence_warning = f" Notice: Input metrics ({', '.join(low_conf)}) have reduced confidence scores."

    status = "PASS" if is_pass else "FAIL"

    if is_pass:
        if d_diff == Decimal("0"):
            explanation = (
                f"Accounting equation holds exactly: Assets (${float(d_assets):,.2f}) = "
                f"Liabilities (${float(d_liabilities):,.2f}) + Equity (${float(d_equity):,.2f}) with zero difference.{confidence_warning}"
            )
        else:
            explanation = (
                f"Accounting equation satisfied within tolerance: Assets (${float(d_assets):,.2f}) vs "
                f"Liabilities + Equity (${float(d_expected):,.2f}). Difference of ${float(d_diff):,.2f} "
                f"({float(d_rel_diff)*100:.3f}%) is within tolerance ${float(d_tolerance):,.2f}.{confidence_warning}"
            )
        failure_reason = None
        recommendation = "Accounting equation verified. Eligible for automated validation pass."
    else:
        explanation = (
            f"Accounting equation failure: Assets (${float(d_assets):,.2f}) differs from "
            f"Liabilities + Equity (${float(d_expected):,.2f}) by ${float(d_diff):,.2f} "
            f"({float(d_rel_diff)*100:.3f}%), exceeding allowable tolerance of ${float(d_tolerance):,.2f}.{confidence_warning}"
        )
        failure_reason = f"Balance sheet discrepancy exceeds tolerance (${float(d_diff):,.2f} > ${float(d_tolerance):,.2f})"
        recommendation = (
            "Auditor review required: inspect balance sheet statement lines for mezzanine equity, "
            "temporary equity, noncontrolling interests, or unaggregated liabilities."
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
        actual_value=float(d_assets),
        absolute_difference=float(d_diff),
        relative_difference=float(d_rel_diff),
        configured_tolerance=float(d_tolerance),
        input_metrics=input_metrics,
        evidence_references=evidence_references,
        explanation=explanation,
        failure_reason=failure_reason,
        recommendation=recommendation,
    )

