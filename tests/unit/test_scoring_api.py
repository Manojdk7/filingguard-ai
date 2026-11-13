import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.repositories.scoring_repository import (
    FilingConfidenceRecord,
    MetricConfidenceRecord,
    ScoringRepository,
)

client = TestClient(app)


@pytest.fixture
def seeded_scoring_records():
    repo = ScoringRepository()
    accn = "test-api-accn-999"

    m_rec = MetricConfidenceRecord(
        accession_number=accn,
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        confidence_score=0.98,
        quality_score_100=98.0,
        status="HIGH",
        review_category="AUTO_PASS",
        factors={
            "evidence_quality": 1.0,
            "concept_mapping_quality": 1.0,
            "period_context_quality": 1.0,
            "unit_quality": 1.0,
            "cross_check_quality": 1.0,
        },
        positive_factors=["Exact cross-source agreement verified"],
        negative_factors=[],
        evidence_references={"accession_number": accn},
        explanation="High confidence revenue extraction",
        review_recommendations=["Auto-pass eligible"],
        version="1.0.0",
    )

    f_rec = FilingConfidenceRecord(
        accession_number=accn,
        cik="0000320193",
        overall_score=0.98,
        quality_score_100=98.0,
        overall_status="HIGH",
        overall_review_category="AUTO_PASS",
        metrics_assessed_count=10,
        metrics_missing_count=0,
        critical_metrics_present=True,
        score_factors={"mean_metric_confidence": 0.98},
        reduction_reasons=[],
        summary_explanation="Filing eligible for AUTO PASS",
        version="1.0.0",
    )

    repo.save_metric_scores([m_rec])
    repo.save_filing_score(f_rec)
    return accn


def test_get_filing_score_not_found():
    response = client.get("/metrics/score/non-existent-accession-000")
    assert response.status_code == 404
    assert "No confidence score found" in response.json()["detail"]


def test_get_metric_score_not_found():
    response = client.get("/metrics/score/test-api-accn-999/metrics/non_existent_metric")
    assert response.status_code == 404


def test_get_filing_score_success(seeded_scoring_records):
    accn = seeded_scoring_records
    response = client.get(f"/metrics/score/{accn}")
    assert response.status_code == 200
    data = response.json()
    assert data["accession_number"] == accn
    assert data["overall_score"] == 0.98
    assert data["overall_status"] == "HIGH"
    assert data["overall_review_category"] == "AUTO_PASS"
    assert len(data["metrics"]) == 1
    assert data["metrics"][0]["metric_id"] == "revenue"


def test_get_single_metric_score_success(seeded_scoring_records):
    accn = seeded_scoring_records
    response = client.get(f"/metrics/score/{accn}/metrics/revenue")
    assert response.status_code == 200
    data = response.json()
    assert data["metric_id"] == "revenue"
    assert data["canonical_name"] == "Revenue"
    assert data["confidence_score"] == 0.98
    assert data["quality_score_100"] == 98.0
    assert data["status"] == "HIGH"
    assert data["review_category"] == "AUTO_PASS"
    assert "Exact cross-source agreement verified" in data["positive_factors"]

