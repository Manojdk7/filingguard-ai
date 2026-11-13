import pytest
from app.extraction.metric_extractor import MetricExtractor
from app.database.repositories.fact_repository import FactRepository


def test_live_company_facts_extraction_apple():
    extractor = MetricExtractor()
    fact_repo = FactRepository()

    # Extract Apple's latest 10-K facts
    report = extractor.extract_metrics_for_filing("320193", use_cache=True, persist=True)

    assert report.cik == "0000320193"
    assert report.accession_number is not None
    assert len(report.metrics) >= 10

    # Require at least 8 valid metrics selected for Apple
    assert report.selected_metrics_count >= 8, f"Expected >= 8 selected metrics, got {report.selected_metrics_count}"

    # Verify key metrics
    metric_map = {m.metric_id: m for m in report.metrics}
    for req in ["revenue", "net_income", "total_assets", "total_liabilities", "stockholders_equity"]:
        m = metric_map[req]
        assert m.status == "selected"
        assert m.selected_value is not None and m.selected_value > 0
        assert m.unit == "USD"
        assert m.concept is not None

    # Verify database persistence
    db_selected = fact_repo.get_selected_facts_by_accession(report.accession_number)
    assert len(db_selected) >= 8

