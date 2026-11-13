"""
Local-database integration test for benchmark and final verification.

Executes the benchmark against cached records for Apple, Microsoft, and Amazon,
persists to SQLite, and validates deterministic results and traceability.
"""
import pytest
from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.reference_loader import load_reference_dataset
from app.database.repositories.benchmark_repository import BenchmarkRepository


def test_live_benchmark_end_to_end():
    """Verify live benchmark execution, persistence, and audit traceability."""
    evaluator = BenchmarkEvaluator()
    bench_repo = BenchmarkRepository()

    # Load verified reference dataset
    all_facts = load_reference_dataset()
    assert len(all_facts) == 52

    # Baseline 3 cached filings in the local test database (28 facts)
    ref_facts = [r for r in all_facts if r.ticker in ("AAPL", "MSFT", "AMZN")]
    assert len(ref_facts) == 28

    # Execute and persist
    report = evaluator.run_benchmark(records=ref_facts, persist=True)

    # 1. Verify summary metrics
    summary = report["reference_summary"]
    assert summary["total_reference_facts"] == 28
    assert summary["company_count"] == 3
    assert summary["filing_count"] == 4
    assert summary["metric_coverage_count"] == 10

    # 2. Verify comparative accuracy
    metrics = report["metrics"]
    fg_metrics = metrics["filingguard"]
    st_metrics = metrics["simple_tag"]

    # All selected cases have cached facts; reference verification provenance is separate.
    assert fg_metrics["accuracy"] == 1.0
    assert fg_metrics["exact_matches"] == 28
    assert fg_metrics["missing_values"] == 0
    assert 0.0 < fg_metrics["evidence_support_rate"] < 1.0
    assert fg_metrics["evidence_supported"] == sum(
        result["has_evidence"] for result in report["detailed_results"]["filingguard"]
    )

    # Simple tag lookup's actual missing rate is measured from the selected records.
    assert st_metrics["accuracy"] < 0.60
    assert st_metrics["missing_values"] == 11
    assert st_metrics["missing_value_rate"] == 11 / 28
    assert st_metrics["evidence_support_rate"] == 0.0
    assert metrics["regex_simulation"]["not_evaluated_cases"] == 28
    assert metrics["regex_simulation"]["accuracy"] is None

    # 3. Verify SQLite persistence and traceability
    persisted_fg = bench_repo.get_results(method="filingguard")
    assert len(persisted_fg) == 28
    for rec in persisted_fg:
        assert rec.test_case_id.startswith("REF-")
        assert rec.result == "PASS"
        assert rec.predicted_value is not None
        assert rec.expected_value == rec.predicted_value

    persisted_st = bench_repo.get_results(method="simple_tag")
    assert len(persisted_st) == 28

    # 4. Verify side-by-side comparison table has no fabricated values
    comp_table = report["comparison_table"]
    assert len(comp_table) == 28
    for row in comp_table:
        assert row["test_case_id"].startswith("REF-")
        assert row["fg_match"] is True
    assert 0 < sum(row["evidence_support"] for row in comp_table) < 28
