import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from app.api.schemas.validation import ValidationResultResponse, ValidationSummaryResponse
from app.database.repositories.validation_repository import ValidationRepository
from app.validation.engine import FinancialValidationEngine

logger = logging.getLogger("filingguard.api.validations")

router = APIRouter(prefix="/validations", tags=["Financial Validations"])


@router.post(
    "/run/{accession_number}",
    response_model=ValidationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Run deterministic financial validation rules on a filing",
)
def run_validations_endpoint(accession_number: str) -> ValidationSummaryResponse:
    """Execute all enabled financial validation rules (accounting equation, operating income, YoY, cross-statement)."""
    clean_accn = accession_number.strip()
    if not clean_accn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid accession number is required.",
        )

    try:
        engine = FinancialValidationEngine()
        results = engine.validate_filing(clean_accn)

        repo = ValidationRepository()
        summary = repo.get_validation_summary(clean_accn)

        val_responses = [
            ValidationResultResponse(
                id=r.id,
                accession_number=r.accession_number,
                cik=r.cik,
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                rule_version=r.rule_version,
                validation_category=r.validation_category,
                status=r.status,
                expected_value=r.expected_value,
                actual_value=r.actual_value,
                absolute_difference=r.absolute_difference,
                relative_difference=r.relative_difference,
                configured_tolerance=r.configured_tolerance,
                input_metrics=r.input_metrics,
                evidence_references=r.evidence_references,
                explanation=r.explanation,
                failure_reason=r.failure_reason,
                recommendation=r.recommendation,
                created_at=r.created_at,
            )
            for r in results
        ]

        return ValidationSummaryResponse(
            accession_number=clean_accn,
            total_rules=summary["total_rules"],
            passed=summary["passed"],
            failed=summary["failed"],
            warnings=summary["warnings"],
            not_evaluated=summary["not_evaluated"],
            validations=val_responses,
        )
    except Exception as e:
        logger.error(f"Error executing validations for {clean_accn}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation engine failure: {str(e)}",
        )


@router.get(
    "/{accession_number}",
    response_model=ValidationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve all validation results for a filing",
)
def get_validations_endpoint(accession_number: str) -> ValidationSummaryResponse:
    """Retrieve existing validation results and summary counts."""
    clean_accn = accession_number.strip()
    repo = ValidationRepository()
    records = repo.get_validations_by_accession(clean_accn)

    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No validation results found for accession '{clean_accn}'. Please run validations first.",
        )

    summary = repo.get_validation_summary(clean_accn)
    val_responses = [
        ValidationResultResponse(
            id=r.id,
            accession_number=r.accession_number,
            cik=r.cik,
            rule_id=r.rule_id,
            rule_name=r.rule_name,
            rule_version=r.rule_version,
            validation_category=r.validation_category,
            status=r.status,
            expected_value=r.expected_value,
            actual_value=r.actual_value,
            absolute_difference=r.absolute_difference,
            relative_difference=r.relative_difference,
            configured_tolerance=r.configured_tolerance,
            input_metrics=r.input_metrics,
            evidence_references=r.evidence_references,
            explanation=r.explanation,
            failure_reason=r.failure_reason,
            recommendation=r.recommendation,
            created_at=r.created_at,
        )
        for r in records
    ]

    return ValidationSummaryResponse(
        accession_number=clean_accn,
        total_rules=summary["total_rules"],
        passed=summary["passed"],
        failed=summary["failed"],
        warnings=summary["warnings"],
        not_evaluated=summary["not_evaluated"],
        validations=val_responses,
    )


@router.get(
    "/{accession_number}/rules/{rule_id}",
    response_model=ValidationResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a specific validation rule result",
)
def get_rule_validation_endpoint(accession_number: str, rule_id: str) -> ValidationResultResponse:
    """Retrieve detailed calculation and explanation for a specific validation rule."""
    clean_accn = accession_number.strip()
    clean_rule_id = rule_id.strip()

    repo = ValidationRepository()
    record = repo.get_validation(clean_accn, clean_rule_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation rule '{clean_rule_id}' not found for accession '{clean_accn}'.",
        )

    return ValidationResultResponse(
        id=record.id,
        accession_number=record.accession_number,
        cik=record.cik,
        rule_id=record.rule_id,
        rule_name=record.rule_name,
        rule_version=record.rule_version,
        validation_category=record.validation_category,
        status=record.status,
        expected_value=record.expected_value,
        actual_value=record.actual_value,
        absolute_difference=record.absolute_difference,
        relative_difference=record.relative_difference,
        configured_tolerance=record.configured_tolerance,
        input_metrics=record.input_metrics,
        evidence_references=record.evidence_references,
        explanation=record.explanation,
        failure_reason=record.failure_reason,
        recommendation=record.recommendation,
        created_at=record.created_at,
    )

