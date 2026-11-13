import pytest
from app.scoring.quality_score import ConfidenceScoringEngine
from app.database.repositories.scoring_repository import ScoringRepository


def test_live_apple_filing_scoring():
    """Score cached Apple filing records and document without contacting SEC."""
    accession_number = "0000320193-26-000026"
    engine = ConfidenceScoringEngine()

    filing_score, metric_scores = engine.score_filing(accession_number)

    # Document integrity verification
    integrity = engine.verify_document_integrity(accession_number)
    assert integrity.exists is True
    assert integrity.hash_matched is True
    assert integrity.calculated_hash == "58c72ba42db6f658d94fbc5248c758d46138d0fba48dceaf6704116205c06eef"

    # Overall filing checks
    assert filing_score.accession_number == accession_number
    assert filing_score.cik == "0000320193"
    assert filing_score.overall_score >= 0.95
    assert filing_score.overall_status == "HIGH"
    assert filing_score.overall_review_category == "AUTO_PASS"
    assert filing_score.metrics_assessed_count == 10
    assert filing_score.metrics_missing_count == 0
    assert filing_score.critical_metrics_present is True

    # Check key canonical metrics
    metric_map = {m.metric_id: m for m in metric_scores}
    assert len(metric_map) == 10

    for m_id in ["revenue", "net_income", "gross_profit", "total_assets", "total_liabilities", "stockholders_equity"]:
        m = metric_map[m_id]
        assert m.confidence_score >= 0.95
        assert m.status == "HIGH"
        assert m.review_category == "AUTO_PASS"
        assert m.factors["source_reliability"] == 0.85
        assert m.factors["cross_source_agreement"] == 1.0
        assert m.factors["period_compatibility"] == 1.0
        assert m.factors["unit_dimensional_compatibility"] == 1.0
        assert m.factors["extraction_mapping_quality"] == 1.0
        assert len(m.positive_factors) >= 3

    # Check database persistence
    scoring_repo = ScoringRepository()
    saved_filing = scoring_repo.get_filing_score(accession_number)
    saved_metrics = scoring_repo.get_metric_scores_by_accession(accession_number)

    assert saved_filing is not None
    assert saved_filing.overall_score == filing_score.overall_score
    assert len(saved_metrics) == 10
