"""
Unit tests for the Benchmark and Accuracy Reports API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_benchmark_summary_api():
    """Verify GET /benchmark/summary returns summary stats and limitations."""
    response = client.get("/benchmark/summary")
    assert response.status_code == 200
    data = response.json()
    assert "reference_summary" in data
    assert "metrics" in data
    assert "limitations" in data
    assert data["reference_summary"]["total_reference_facts"] >= 20
    assert "filingguard" in data["metrics"]
    assert "simple_tag" in data["metrics"]
    assert "llm_baseline" in data["metrics"]


def test_get_benchmark_report_api():
    """Verify GET /benchmark/report returns full benchmark report."""
    response = client.get("/benchmark/report")
    assert response.status_code == 200
    data = response.json()
    assert "reference_summary" in data
    assert "metrics" in data
    assert "comparison_table" in data
    assert len(data["comparison_table"]) >= 20


def test_get_benchmark_results_filter_api():
    """Verify GET /benchmark/results with and without method filter."""
    # All results
    resp_all = client.get("/benchmark/results")
    assert resp_all.status_code == 200
    items = resp_all.json()
    assert len(items) > 0

    # Filtered by method
    resp_fg = client.get("/benchmark/results?method=filingguard")
    assert resp_fg.status_code == 200
    fg_items = resp_fg.json()
    assert all(i["method"] == "filingguard" for i in fg_items)

    # Invalid method filter
    resp_inv = client.get("/benchmark/results?method=invalid_xyz")
    assert resp_inv.status_code == 400


def test_get_benchmark_comparison_api():
    """Verify GET /benchmark/comparison returns side-by-side rows."""
    response = client.get("/benchmark/comparison")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 20
    first = rows[0]
    assert "test_case_id" in first
    assert "company" in first
    assert "expected_value" in first
    assert "fg_match" in first
    assert "simple_match" in first


def test_run_benchmark_post_api():
    """Verify POST /benchmark/run executes and persists benchmark."""
    response = client.post("/benchmark/run")
    assert response.status_code == 200
    data = response.json()
    metrics = data["metrics"]["filingguard"]
    assert metrics["total_cases"] == data["reference_summary"]["total_reference_facts"]
    assert metrics["accuracy"] == metrics["exact_matches"] / metrics["evaluated_cases"]
    assert metrics["missing_values"] > 0
    assert data["metrics"]["regex_simulation"]["not_evaluated_cases"] == metrics["total_cases"]
