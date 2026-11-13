import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from app.api.schemas.metric import FilingScoreResponse, MetricScoreResponse
from app.database.repositories.scoring_repository import ScoringRepository
from app.scoring.quality_score import ConfidenceScoringEngine

logger = logging.getLogger("filingguard.api.metrics")

router = APIRouter(prefix="/metrics", tags=["Metrics & Confidence Scoring"])


@router.post(
    "/score/{accession_number}",
    response_model=FilingScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate and persist confidence scores for a filing",
)
def score_filing_endpoint(accession_number: str) -> FilingScoreResponse:
    """Execute deterministic evidence and confidence evaluation for all canonical metrics in a filing."""
    clean_accn = accession_number.strip()
    if not clean_accn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid filing accession number is required.",
        )

    try:
        engine = ConfidenceScoringEngine()
        filing_score, metric_scores = engine.score_filing(clean_accn)

        metric_responses = [
            MetricScoreResponse(
                metric_id=m.metric_id,
                canonical_name=m.canonical_name,
                confidence_score=m.confidence_score,
                quality_score_100=m.quality_score_100,
                status=m.status,
                review_category=m.review_category,
                factors=m.factors,
                positive_factors=m.positive_factors,
                negative_factors=m.negative_factors,
                evidence_references=m.evidence_references,
                explanation=m.explanation,
                review_recommendations=m.review_recommendations,
                version=m.version,
                created_at=m.created_at,
            )
            for m in metric_scores
        ]

        return FilingScoreResponse(
            accession_number=filing_score.accession_number,
            cik=filing_score.cik,
            overall_score=filing_score.overall_score,
            quality_score_100=filing_score.quality_score_100,
            overall_status=filing_score.overall_status,
            overall_review_category=filing_score.overall_review_category,
            metrics_assessed_count=filing_score.metrics_assessed_count,
            metrics_missing_count=filing_score.metrics_missing_count,
            critical_metrics_present=filing_score.critical_metrics_present,
            score_factors=filing_score.score_factors,
            reduction_reasons=filing_score.reduction_reasons,
            summary_explanation=filing_score.summary_explanation,
            version=filing_score.version,
            created_at=filing_score.created_at,
            metrics=metric_responses,
        )
    except Exception as e:
        logger.error(f"Error scoring filing {clean_accn}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scoring engine failure: {str(e)}",
        )


@router.get(
    "/score/{accession_number}",
    response_model=FilingScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve stored filing confidence score and factor breakdown",
)
def get_filing_score_endpoint(accession_number: str) -> FilingScoreResponse:
    """Retrieve existing filing confidence score and associated metric confidence scores."""
    clean_accn = accession_number.strip()
    scoring_repo = ScoringRepository()
    filing_score = scoring_repo.get_filing_score(clean_accn)

    if not filing_score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No confidence score found for accession number '{clean_accn}'. Please score the filing first.",
        )

    metric_scores = scoring_repo.get_metric_scores_by_accession(clean_accn)
    metric_responses = [
        MetricScoreResponse(
            metric_id=m.metric_id,
            canonical_name=m.canonical_name,
            confidence_score=m.confidence_score,
            quality_score_100=m.quality_score_100,
            status=m.status,
            review_category=m.review_category,
            factors=m.factors,
            positive_factors=m.positive_factors,
            negative_factors=m.negative_factors,
            evidence_references=m.evidence_references,
            explanation=m.explanation,
            review_recommendations=m.review_recommendations,
            version=m.version,
            created_at=m.created_at,
        )
        for m in metric_scores
    ]

    return FilingScoreResponse(
        accession_number=filing_score.accession_number,
        cik=filing_score.cik,
        overall_score=filing_score.overall_score,
        quality_score_100=filing_score.quality_score_100,
        overall_status=filing_score.overall_status,
        overall_review_category=filing_score.overall_review_category,
        metrics_assessed_count=filing_score.metrics_assessed_count,
        metrics_missing_count=filing_score.metrics_missing_count,
        critical_metrics_present=filing_score.critical_metrics_present,
        score_factors=filing_score.score_factors,
        reduction_reasons=filing_score.reduction_reasons,
        summary_explanation=filing_score.summary_explanation,
        version=filing_score.version,
        created_at=filing_score.created_at,
        metrics=metric_responses,
    )


@router.get(
    "/score/{accession_number}/metrics/{metric_id}",
    response_model=MetricScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve confidence score for a single metric",
)
def get_metric_score_endpoint(accession_number: str, metric_id: str) -> MetricScoreResponse:
    """Retrieve detailed factor breakdown and explanation for a specific metric."""
    clean_accn = accession_number.strip()
    clean_metric_id = metric_id.strip()

    scoring_repo = ScoringRepository()
    m = scoring_repo.get_metric_score(clean_accn, clean_metric_id)

    if not m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Confidence score not found for metric '{clean_metric_id}' in accession '{clean_accn}'.",
        )

    return MetricScoreResponse(
        metric_id=m.metric_id,
        canonical_name=m.canonical_name,
        confidence_score=m.confidence_score,
        quality_score_100=m.quality_score_100,
        status=m.status,
        review_category=m.review_category,
        factors=m.factors,
        positive_factors=m.positive_factors,
        negative_factors=m.negative_factors,
        evidence_references=m.evidence_references,
        explanation=m.explanation,
        review_recommendations=m.review_recommendations,
        version=m.version,
        created_at=m.created_at,
    )

