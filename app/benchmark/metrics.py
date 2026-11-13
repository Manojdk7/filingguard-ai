"""
Benchmark evaluation metrics computation for Phase 11.

Computes accuracy, precision, recall, and detailed comparison metrics
across benchmark methods.
"""
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger("filingguard.benchmark.metrics")


class BenchmarkResult(BaseModel):
    """Result of evaluating a single reference fact against one method."""
    test_case_id: str
    method: str  # 'simple_tag', 'llm_baseline', 'filingguard'
    metric_id: str
    accession_number: str
    company: str
    expected_value: float
    expected_unit: str
    expected_period: str  # period_end from reference
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
    error_type: Optional[str] = None  # 'missing', 'value_mismatch', 'period_mismatch', etc.
    notes: Optional[str] = None


class MethodMetrics(BaseModel):
    """Aggregated metrics for one extraction method."""
    method: str
    total_cases: int = 0
    evaluated_cases: int = 0
    not_evaluated_cases: int = 0
    predictions_returned: int = 0
    exact_matches: int = 0
    value_matches: int = 0
    unit_matches: int = 0
    period_matches: int = 0
    concept_matches: int = 0
    evidence_supported: int = 0
    missing_values: int = 0
    value_mismatches: int = 0

    # Rates
    accuracy: Optional[float] = None
    evaluated_accuracy: Optional[float] = None
    value_match_rate: Optional[float] = None
    unit_accuracy: Optional[float] = None
    period_accuracy: Optional[float] = None
    evidence_support_rate: Optional[float] = None
    missing_value_rate: Optional[float] = None
    false_positive_rate: Optional[float] = None

    # Anomaly detection metrics
    anomaly_true_positives: int = 0
    anomaly_false_positives: int = 0
    anomaly_false_negatives: int = 0
    anomaly_true_negatives: int = 0
    anomaly_precision: Optional[float] = None
    anomaly_recall: Optional[float] = None


# ---------------------------------------------------------------------------
# Value comparison helper
# ---------------------------------------------------------------------------

VALUE_TOLERANCE = 1.0  # absolute difference ≤ 1.0 = exact match


def values_match(expected: float, predicted: Optional[float]) -> bool:
    """Check if two financial values match within tolerance."""
    if predicted is None:
        return False
    return abs(expected - predicted) <= VALUE_TOLERANCE


# ---------------------------------------------------------------------------
# Core metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(
    results: List[BenchmarkResult],
    anomaly_flags: Optional[Dict[str, bool]] = None,
) -> MethodMetrics:
    """Compute aggregated accuracy metrics for a list of benchmark results.

    All results **must** belong to the same method.

    Args:
        results: List of BenchmarkResult objects (single method).
        anomaly_flags: Optional dict mapping test_case_id → whether the
            reference fact is flagged as anomalous (``has_anomaly``).
    
    Returns:
        MethodMetrics with computed rates and counts.
    """
    if not results:
        return MethodMetrics(method="unknown")

    method = results[0].method
    m = MethodMetrics(method=method, total_cases=len(results))

    for r in results:
        if r.error_type == "not_evaluated":
            m.not_evaluated_cases += 1
            continue
        m.evaluated_cases += 1
        if r.predicted_value is None:
            m.missing_values += 1
            continue
        m.predictions_returned += 1

        if r.is_value_match:
            m.value_matches += 1
        else:
            m.value_mismatches += 1

        if r.is_unit_match:
            m.unit_matches += 1
        if r.is_period_match:
            m.period_matches += 1
        if r.is_concept_match:
            m.concept_matches += 1
        if r.has_evidence:
            m.evidence_supported += 1

        # "Exact match" = value + unit + period all correct
        if r.is_value_match and r.is_unit_match and r.is_period_match:
            m.exact_matches += 1

    # Missing predictions count as failures; unevaluated cases have no metric denominator.
    n = m.evaluated_cases
    predictions = m.predictions_returned
    if n:
        m.accuracy = m.exact_matches / n
        m.value_match_rate = m.value_matches / n
        m.missing_value_rate = m.missing_values / n
    if predictions:
        m.evaluated_accuracy = m.exact_matches / predictions
        m.unit_accuracy = m.unit_matches / predictions
        m.period_accuracy = m.period_matches / predictions
        m.evidence_support_rate = m.evidence_supported / predictions
        m.false_positive_rate = m.value_mismatches / predictions

    # Anomaly precision/recall
    if anomaly_flags:
        for r in results:
            if r.error_type == "not_evaluated":
                continue
            is_anomaly_ref = anomaly_flags.get(r.test_case_id, False)
            # A prediction is "flagged as anomaly" if value doesn't match AND value exists
            is_flagged = (r.predicted_value is not None and not r.is_value_match)

            if is_anomaly_ref and is_flagged:
                m.anomaly_true_positives += 1
            elif not is_anomaly_ref and is_flagged:
                m.anomaly_false_positives += 1
            elif is_anomaly_ref and not is_flagged:
                m.anomaly_false_negatives += 1
            else:
                m.anomaly_true_negatives += 1

        tp = m.anomaly_true_positives
        fp = m.anomaly_false_positives
        fn = m.anomaly_false_negatives
        if tp + fp:
            m.anomaly_precision = tp / (tp + fp)
        if tp + fn:
            m.anomaly_recall = tp / (tp + fn)

    return m


def compute_per_metric_breakdown(
    results: List[BenchmarkResult],
) -> Dict[str, Dict[str, Any]]:
    """Compute per-metric accuracy breakdown for a single method.
    
    Returns a dict keyed by metric_id with value/unit/period match counts.
    """
    breakdown: Dict[str, Dict[str, Any]] = {}
    for r in results:
        entry = breakdown.setdefault(r.metric_id, {
            "total": 0, "evaluated": 0, "not_evaluated": 0,
            "value_matches": 0, "unit_matches": 0,
            "period_matches": 0, "missing": 0, "exact_matches": 0,
        })
        entry["total"] += 1
        if r.error_type == "not_evaluated":
            entry["not_evaluated"] += 1
            continue
        entry["evaluated"] += 1
        if r.predicted_value is None:
            entry["missing"] += 1
            continue
        if r.is_value_match:
            entry["value_matches"] += 1
        if r.is_unit_match:
            entry["unit_matches"] += 1
        if r.is_period_match:
            entry["period_matches"] += 1
        if r.is_value_match and r.is_unit_match and r.is_period_match:
            entry["exact_matches"] += 1
    return breakdown


def compute_per_company_breakdown(
    results: List[BenchmarkResult],
) -> Dict[str, Dict[str, Any]]:
    """Compute per-company accuracy breakdown for a single method."""
    breakdown: Dict[str, Dict[str, Any]] = {}
    for r in results:
        entry = breakdown.setdefault(r.company, {
            "total": 0, "evaluated": 0, "not_evaluated": 0,
            "exact_matches": 0, "missing": 0,
        })
        entry["total"] += 1
        if r.error_type == "not_evaluated":
            entry["not_evaluated"] += 1
            continue
        entry["evaluated"] += 1
        if r.predicted_value is None:
            entry["missing"] += 1
        elif r.is_value_match and r.is_unit_match and r.is_period_match:
            entry["exact_matches"] += 1
    return breakdown
