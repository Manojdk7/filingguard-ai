"""
Pydantic schemas for the Phase 11 Benchmark and Verification API.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel


class ReferenceSummarySchema(BaseModel):
    total_reference_facts: int
    companies: List[str]
    company_count: int
    filing_count: int
    accession_numbers: List[str]
    metrics_covered: List[str]
    metric_coverage_count: int
    anomaly_count: int
    all_reviewer_verified: bool
    reviewer_verified_count: int
    reviewer_verification_status: str
    source_url_count: int
    evidence_locator_count: int
    verification_method_count: int
    independent_review_method_documented: bool


class MethodMetricsSchema(BaseModel):
    method: str
    total_cases: int
    evaluated_cases: int
    not_evaluated_cases: int
    predictions_returned: int
    exact_matches: int
    value_matches: int
    unit_matches: int
    period_matches: int
    concept_matches: int
    evidence_supported: int
    missing_values: int
    value_mismatches: int
    accuracy: Optional[float]
    evaluated_accuracy: Optional[float] = None
    value_match_rate: Optional[float]
    unit_accuracy: Optional[float]
    period_accuracy: Optional[float]
    evidence_support_rate: Optional[float]
    missing_value_rate: Optional[float]
    false_positive_rate: Optional[float]
    anomaly_true_positives: int
    anomaly_false_positives: int
    anomaly_false_negatives: int
    anomaly_true_negatives: int
    anomaly_precision: Optional[float]
    anomaly_recall: Optional[float]


class BenchmarkResultItemSchema(BaseModel):
    test_case_id: str
    method: str
    metric_id: str
    accession_number: str
    company: str
    expected_value: float
    expected_unit: str
    expected_period: str
    expected_concept: str
    predicted_value: Optional[float] = None
    predicted_unit: Optional[str] = None
    predicted_period: Optional[str] = None
    predicted_concept: Optional[str] = None
    has_evidence: bool = False
    is_value_match: bool = False
    is_unit_match: bool = False
    is_period_match: bool = False
    is_concept_match: bool = False
    error_type: Optional[str] = None
    notes: Optional[str] = None


class ComparisonRowSchema(BaseModel):
    test_case_id: str
    company: str
    metric_id: str
    expected_value: float
    simple_predicted: Optional[float] = None
    simple_match: bool = False
    llm_predicted: Optional[float] = None
    llm_match: bool = False
    regex_predicted: Optional[float] = None
    regex_match: bool = False
    fg_predicted: Optional[float] = None
    fg_match: bool = False
    evidence_support: bool = False


class BenchmarkReportResponse(BaseModel):
    reference_summary: ReferenceSummarySchema
    metrics: Dict[str, MethodMetricsSchema]
    comparison_table: List[ComparisonRowSchema]
    limitations: List[str]
