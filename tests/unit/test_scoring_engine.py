import os
import tempfile
import sqlite3
from unittest.mock import MagicMock
import pytest

from app.database.models import init_db
from app.database.repositories.document_repository import DownloadedFiling
from app.database.repositories.fact_repository import FactRecord
from app.database.repositories.reconciliation_repository import (
    CustomConceptCandidateRecord,
    ReconciliationRecord,
)
from app.database.repositories.scoring_repository import (
    FilingConfidenceRecord,
    MetricConfidenceRecord,
    ScoringRepository,
)
from app.extraction.taxonomy_mapping import MetricDefinition, TaxonomyMappingManager
from app.scoring.escalation import AUTO_PASS, MANDATORY_REVIEW, REVIEW_RECOMMENDED
from app.scoring.quality_score import ConfidenceScoringEngine, DocumentIntegrityResult


@pytest.fixture
def sample_metric():
    return MetricDefinition(
        metric_id="revenue",
        canonical_name="Revenue",
        statement="income_statement",
        period_type="duration",
        default_unit="USD",
        is_consolidated_only=True,
        concepts=["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        description="Total revenue",
    )


@pytest.fixture
def mock_integrity():
    return DocumentIntegrityResult(
        exists=True,
        hash_matched=True,
        calculated_hash="abc123hash",
        stored_hash="abc123hash",
        local_path="data/filings/test.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/test.htm",
        accession_number="0000320193-26-000026",
        cik="0000320193",
        notes="Document integrity verified",
    )


def test_exact_agreement_between_sources(sample_metric, mock_integrity):
    """Test 1: Exact agreement between Company Facts and iXBRL produces high confidence score."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Exact annual match",
    )

    recon = ReconciliationRecord(
        accession_number="0000320193-26-000026",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        status="exact_match",
        company_facts_value=478800000000.0,
        ixbrl_value=478800000000.0,
        difference=0.0,
        company_facts_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        ixbrl_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        company_facts_unit="USD",
        ixbrl_unit="USD",
        company_facts_period="2025-09-28 to 2026-09-26",
        ixbrl_period="2025-09-28 to 2026-09-26",
        is_segment_mismatch=False,
        explanation="Exact match",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=recon,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.confidence_score >= 0.95
    assert score.status == "HIGH"
    assert score.review_category == AUTO_PASS
    assert score.factors["source_reliability"] == 0.85
    assert score.factors["cross_source_agreement"] == 1.0
    assert score.factors["extraction_mapping_quality"] == 1.0
    assert score.factors["period_compatibility"] == 1.0
    assert score.factors["unit_dimensional_compatibility"] == 1.0
    assert score.confidence_score == 0.955
    breakdown = score.evidence_references["factor_breakdown"]
    assert breakdown["source_reliability"]["weighted_contribution"] == 0.255
    assert breakdown["source_reliability"]["deduction_reasons"]
    assert round(
        sum(factor["weighted_contribution"] for factor in breakdown.values()), 4
    ) == score.confidence_score


def test_numeric_mismatch_escalates(sample_metric, mock_integrity):
    """Test 2: Numeric mismatch between SEC sources reduces cross-check and triggers mandatory review."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Exact annual match",
    )

    recon = ReconciliationRecord(
        accession_number="0000320193-26-000026",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        status="value_mismatch",
        company_facts_value=478800000000.0,
        ixbrl_value=450000000000.0,
        difference=28800000000.0,
        company_facts_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        ixbrl_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        company_facts_unit="USD",
        ixbrl_unit="USD",
        is_segment_mismatch=False,
        explanation="Value mismatch",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=recon,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.factors["cross_source_agreement"] == 0.15
    assert score.review_category == MANDATORY_REVIEW
    assert any("Value mismatch" in n for n in score.negative_factors)


def test_missing_metric_scores_zero(sample_metric, mock_integrity):
    """Test 3: Missing metric receives 0.0 confidence and mandatory review."""
    engine = ConfidenceScoringEngine()

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=None,
        recon_record=None,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.confidence_score == 0.0
    assert score.status == "LOW"
    assert score.review_category == MANDATORY_REVIEW
    assert any("Metric absent" in n for n in score.negative_factors)


def test_ambiguous_metric_reduces_score_and_triggers_review(sample_metric, mock_integrity):
    """Test 4: Ambiguous metric penalizes mapping quality and triggers review."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="ambiguous",
        selection_explanation="Multiple candidates",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.factors["extraction_mapping_quality"] == 0.30
    assert score.review_category == MANDATORY_REVIEW
    assert any("Multiple competing candidate facts" in r for r in score.negative_factors)


def test_custom_taxonomy_candidate_for_review(sample_metric, mock_integrity):
    """Test 5: Custom taxonomy candidate receives 0.50 mapping score and mandatory review."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="aapl",
        concept="CustomNetRevenue",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="candidate",
        selection_explanation="Custom extension candidate",
    )

    candidate = CustomConceptCandidateRecord(
        accession_number="0000320193-26-000026",
        custom_concept="CustomNetRevenue",
        namespace="http://www.apple.com/20260926",
        candidate_metric_id="revenue",
        candidate_metric_name="Revenue",
        confidence_level="candidate_for_review",
        reason="Semantic similarity",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[candidate],
        integrity_result=mock_integrity,
    )

    assert score.factors["extraction_mapping_quality"] == 0.50
    assert score.review_category == MANDATORY_REVIEW
    assert any("candidate_for_review" in r for r in score.negative_factors)


def test_unresolved_taxonomy_mapping(sample_metric, mock_integrity):
    """Test 6: Unresolved custom taxonomy mapping receives 0.10 score and triggers review."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="aapl",
        concept="UnresolvedRevenueExtension",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="candidate",
        selection_explanation="Unresolved custom tag",
    )

    candidate = CustomConceptCandidateRecord(
        accession_number="0000320193-26-000026",
        custom_concept="UnresolvedRevenueExtension",
        namespace="http://www.apple.com/20260926",
        candidate_metric_id="revenue",
        candidate_metric_name="Revenue",
        confidence_level="unresolved",
        reason="Unknown semantics",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[candidate],
        integrity_result=mock_integrity,
    )

    assert score.factors["extraction_mapping_quality"] == 0.10
    assert score.review_category == MANDATORY_REVIEW


def test_dimensional_fact_exclusion(sample_metric, mock_integrity):
    """Test 7: Dimensional segment fact is barred from receiving consolidated confidence."""
    engine = ConfidenceScoringEngine()

    recon = ReconciliationRecord(
        accession_number="0000320193-26-000026",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        status="segment_vs_consolidated_mismatch",
        is_segment_mismatch=True,
        explanation="Segment disclosure cannot map to consolidated total",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=None,
        recon_record=recon,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.factors["extraction_mapping_quality"] == 0.0
    assert score.factors["cross_source_agreement"] == 0.0
    assert score.review_category == MANDATORY_REVIEW
    assert any("Dimensional segment-level fact excluded" in r for r in score.negative_factors)


def test_period_mismatch_reduces_score_and_triggers_review(sample_metric, mock_integrity):
    """Test 8: Incompatible period (e.g. quarterly duration for annual metric) scores 0.0 and triggers review."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=120000000000.0,
        normalized_value=120000000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2026-06-28",
        period_end="2026-09-26",  # ~90 days (quarterly)
        fiscal_year=2026,
        fiscal_period="Q4",
        form="10-K",
        status="selected",
        selection_explanation="Quarterly fact",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.factors["period_compatibility"] == 0.0
    assert score.review_category == MANDATORY_REVIEW
    assert any("Quarterly period" in r for r in score.negative_factors)


@pytest.mark.parametrize(
    ("period_start", "expected_score"),
    [(None, 0.0), ("2026-01-01", 0.5)],
)
def test_incomplete_or_nonannual_duration_never_passes(sample_metric, mock_integrity, period_start, expected_score):
    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=100.0,
        normalized_value=100.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start=period_start,
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="test duration",
    )

    score = ConfidenceScoringEngine().calculate_metric_confidence(
        metric=sample_metric,
        accession_number=fact.accession_number,
        cik=fact.cik,
        target_report_period=fact.period_end,
        company_fact=fact,
        recon_record=None,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.factors["period_compatibility"] == expected_score
    assert score.review_category == MANDATORY_REVIEW


def test_unit_mismatch_reduces_score_and_triggers_review(sample_metric, mock_integrity):
    """Test 9: Invalid or non-USD unit for monetary metric scores 0.0 and triggers review."""
    engine = ConfidenceScoringEngine()

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="shares",  # Invalid unit for revenue!
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Shares unit",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[],
        integrity_result=mock_integrity,
    )

    assert score.factors["unit_dimensional_compatibility"] == 0.0
    assert score.review_category == MANDATORY_REVIEW
    assert any("Expected unit USD" in r for r in score.negative_factors)


def test_modified_document_hash_fails_integrity(sample_metric):
    """Test 10: Modified or invalid document hash severely reduces evidence quality and flags review."""
    engine = ConfidenceScoringEngine()

    failed_integrity = DocumentIntegrityResult(
        exists=True,
        hash_matched=False,
        calculated_hash="tampered_hash_value",
        stored_hash="original_hash_value",
        local_path="data/filings/tampered.htm",
        notes="Integrity failure: calculated hash does not match stored hash",
    )

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Annual match",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[],
        integrity_result=failed_integrity,
    )

    assert score.factors["source_reliability"] == 0.0
    assert score.review_category == MANDATORY_REVIEW
    assert any("failed its SHA-256" in r for r in score.negative_factors)


def test_missing_original_filing_handled_gracefully(sample_metric):
    """Test 11: Missing original filing document reduces evidence quality and triggers review."""
    engine = ConfidenceScoringEngine()

    missing_integrity = DocumentIntegrityResult(
        exists=False,
        hash_matched=False,
        notes="Document file not found at expected local path",
    )

    fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=478800000000.0,
        normalized_value=478800000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2025-09-28",
        period_end="2026-09-26",
        fiscal_year=2026,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Annual match",
    )

    score = engine.calculate_metric_confidence(
        metric=sample_metric,
        accession_number="0000320193-26-000026",
        cik="0000320193",
        target_report_period="2026-09-26",
        company_fact=fact,
        recon_record=None,
        custom_candidates=[],
        integrity_result=missing_integrity,
    )

    assert score.factors["source_reliability"] == 0.55
    assert score.review_category == MANDATORY_REVIEW
    assert any("not available for local integrity verification" in r for r in score.negative_factors)


def test_filing_level_aggregation_with_incomplete_metrics():
    """Test 12: Filing-level aggregation distinguishes incomplete assessment from high confidence."""
    engine = ConfidenceScoringEngine()

    # Create 8 high confidence metrics, 2 missing metrics (e.g. Total Liabilities and Gross Profit missing)
    metric_scores = []
    all_metrics = engine.taxonomy_manager.get_all_metrics()

    for idx, m in enumerate(all_metrics):
        if m.metric_id in ("gross_profit", "total_liabilities"):
            # Missing metric
            score = MetricConfidenceRecord(
                accession_number="test-accn",
                cik="0001018724",
                metric_id=m.metric_id,
                canonical_name=m.canonical_name,
                confidence_score=0.0,
                quality_score_100=0.0,
                status="LOW",
                review_category=MANDATORY_REVIEW,
                factors={"evidence_quality": 0, "concept_mapping_quality": 0, "period_context_quality": 0, "unit_quality": 0, "cross_check_quality": 0},
                positive_factors=[],
                negative_factors=["Missing metric"],
                evidence_references={},
                explanation="Missing",
                review_recommendations=["Inspect disclosures"],
            )
        else:
            score = MetricConfidenceRecord(
                accession_number="test-accn",
                cik="0001018724",
                metric_id=m.metric_id,
                canonical_name=m.canonical_name,
                confidence_score=0.98,
                quality_score_100=98.0,
                status="HIGH",
                review_category=AUTO_PASS,
                factors={"evidence_quality": 1, "concept_mapping_quality": 1, "period_context_quality": 1, "unit_quality": 1, "cross_check_quality": 1},
                positive_factors=["Exact match"],
                negative_factors=[],
                evidence_references={},
                explanation="Exact match",
                review_recommendations=[],
            )
        metric_scores.append(score)

    filing_score = engine.calculate_filing_confidence(
        accession_number="test-accn",
        cik="0001018724",
        metric_scores=metric_scores,
    )

    assert filing_score.metrics_assessed_count == 8
    assert filing_score.metrics_missing_count == 2
    assert filing_score.critical_metrics_present is False  # total_liabilities is critical
    assert filing_score.overall_review_category == MANDATORY_REVIEW
    assert any("INCOMPLETE" in r for r in filing_score.reduction_reasons)


def test_repeated_scoring_and_persistence_idempotency():
    """Test 13: Repeated scoring does not produce duplicate records."""
    repo = ScoringRepository()
    accn = "test-idempotent-accn-001"

    metric_record = MetricConfidenceRecord(
        accession_number=accn,
        cik="0000000001",
        metric_id="revenue",
        canonical_name="Revenue",
        confidence_score=0.96,
        quality_score_100=96.0,
        status="HIGH",
        review_category=AUTO_PASS,
        factors={"evidence_quality": 1.0, "concept_mapping_quality": 1.0, "period_context_quality": 1.0, "unit_quality": 1.0, "cross_check_quality": 1.0},
        positive_factors=["Exact match"],
        negative_factors=[],
        evidence_references={},
        explanation="Test",
        review_recommendations=[],
    )

    filing_record = FilingConfidenceRecord(
        accession_number=accn,
        cik="0000000001",
        overall_score=0.96,
        quality_score_100=96.0,
        overall_status="HIGH",
        overall_review_category=AUTO_PASS,
        metrics_assessed_count=10,
        metrics_missing_count=0,
        critical_metrics_present=True,
        score_factors={"mean": 0.96},
        reduction_reasons=[],
        summary_explanation="Passed",
    )

    # Save once
    repo.save_metric_scores([metric_record])
    repo.save_filing_score(filing_record)

    # Save twice (repeat)
    repo.save_metric_scores([metric_record])
    repo.save_filing_score(filing_record)

    fetched_metrics = repo.get_metric_scores_by_accession(accn)
    fetched_filing = repo.get_filing_score(accn)

    assert len(fetched_metrics) == 1
    assert fetched_filing is not None
    assert fetched_filing.overall_score == 0.96
