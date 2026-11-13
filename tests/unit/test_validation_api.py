import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.repositories.validation_repository import ValidationRecord, ValidationRepository

client = TestClient(app)


@pytest.fixture
def seeded_validation_record():
    repo = ValidationRepository()
    accn = "test-val-api-accn-888"

    rec = ValidationRecord(
        accession_number=accn,
        cik="0000320193",
        rule_id="balance_sheet_equation",
        rule_name="Accounting Equation",
        rule_version="1.0.0",
        validation_category="balance_sheet",
        status="PASS",
        expected_value=400000000000.0,
        actual_value=400000000000.0,
        absolute_difference=0.0,
        relative_difference=0.0,
        configured_tolerance=1000000.0,
        input_metrics={"assets": 400000000000.0},
        evidence_references={"test": "seed"},
        explanation="Holds exactly",
        recommendation="No action needed",
    )
    repo.save_validations([rec])
    return accn


def test_get_validations_not_found():
    response = client.get("/validations/non-existent-accession-000")
    assert response.status_code == 404
    assert "No validation results found" in response.json()["detail"]


def test_get_rule_validation_not_found():
    response = client.get("/validations/test-val-api-accn-888/rules/non_existent_rule")
    assert response.status_code == 404


def test_get_validations_success(seeded_validation_record):
    accn = seeded_validation_record
    response = client.get(f"/validations/{accn}")
    assert response.status_code == 200
    data = response.json()
    assert data["accession_number"] == accn
    assert data["total_rules"] == 1
    assert data["passed"] == 1
    assert data["failed"] == 0
    assert len(data["validations"]) == 1
    assert data["validations"][0]["rule_id"] == "balance_sheet_equation"


def test_get_single_rule_validation_success(seeded_validation_record):
    accn = seeded_validation_record
    response = client.get(f"/validations/{accn}/rules/balance_sheet_equation")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "balance_sheet_equation"
    assert data["status"] == "PASS"
    assert data["absolute_difference"] == 0.0

