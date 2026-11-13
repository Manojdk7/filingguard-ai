from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MetricScoreResponse(BaseModel):
    metric_id: str
    canonical_name: str
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Normalized score 0.0 to 1.0")
    quality_score_100: float = Field(..., ge=0.0, le=100.0, description="Scaled quality score 0 to 100")
    status: str = Field(..., description="HIGH, MEDIUM, or LOW")
    review_category: str = Field(..., description="AUTO_PASS, REVIEW_RECOMMENDED, or MANDATORY_REVIEW")
    factors: Dict[str, float]
    positive_factors: List[str]
    negative_factors: List[str]
    evidence_references: Dict[str, Any]
    explanation: str
    review_recommendations: List[str]
    version: str = "1.0.0"
    created_at: Optional[str] = None


class FilingScoreResponse(BaseModel):
    accession_number: str
    cik: str
    overall_score: float = Field(..., ge=0.0, le=1.0)
    quality_score_100: float = Field(..., ge=0.0, le=100.0)
    overall_status: str
    overall_review_category: str
    metrics_assessed_count: int
    metrics_missing_count: int
    critical_metrics_present: bool
    score_factors: Dict[str, float]
    reduction_reasons: List[str]
    summary_explanation: str
    version: str = "1.0.0"
    created_at: Optional[str] = None
    metrics: Optional[List[MetricScoreResponse]] = None

