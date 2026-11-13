"""
Unit tests for Phase 11 Benchmark and Final Verification Engine.
"""
import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.benchmark.reference_loader import (
    ReferenceRecord,
    get_reference_summary,
    group_by_accession,
    load_reference_dataset,
)
from app.benchmark.metrics import (
    BenchmarkResult,
    MethodMetrics,
    compute_metrics,
    compute_per_company_breakdown,
    compute_per_metric_breakdown,
    values_match,
)
from app.benchmark.evaluator import BenchmarkEvaluator
from app.database.repositories.benchmark_repository import (
    BenchmarkRepository,
    BenchmarkResultRecord,
)
from app.database.repositories.fact_repository import FactRecord
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact


def test_reference_dataset_loads_correctly():
    """Verify reference facts dataset loads, validates, and has expected records."""
    records = load_reference_dataset()
    assert len(records) >= 20
    assert all(isinstance(r, ReferenceRecord) for r in records)
    assert all(r.reviewer_verified for r in records)

    # Check required fields on sample record
    rec = records[0]
    assert rec.test_case_id.startswith("REF-")
    assert rec.ticker in ["AAPL", "MSFT", "AMZN"]
    assert rec.accession_number
    assert rec.expected_value > 0
    assert rec.expected_unit == "USD"
    assert rec.period_type in ["instant", "duration"]


def test_reference_summary_and_grouping():
    """Verify reference dataset summary calculations and grouping."""
    records = load_reference_dataset()
    summary = get_reference_summary(records)

    assert summary["total_reference_facts"] == len(records)
    assert summary["company_count"] == 6
    assert "AAPL" in summary["companies"]
    assert "MSFT" in summary["companies"]
    assert "AMZN" in summary["companies"]
    assert "WMT" in summary["companies"]
    assert "XOM" in summary["companies"]
    assert "TSLA" in summary["companies"]
    assert summary["metric_coverage_count"] == 10
    assert summary["all_reviewer_verified"] is True
    assert summary["reviewer_verified_count"] == len(records)
    assert summary["reviewer_verification_status"] == "not_independently_audited"
    assert summary["source_url_count"] == 0
    assert summary["evidence_locator_count"] == 0
    assert summary["verification_method_count"] == 0
    assert summary["independent_review_method_documented"] is False

    grouped = group_by_accession(records)
    assert len(grouped) == 7
    for accn, rec_list in grouped.items():
        assert len(rec_list) > 0


def test_values_match_tolerance():
    """Verify numeric value matching tolerance logic."""
    assert values_match(100.0, 100.0) is True
    assert values_match(100.0, 100.5) is True
    assert values_match(100.0, 101.0) is True
    assert values_match(100.0, 101.01) is False
    assert values_match(100.0, None) is False


def test_compute_metrics_calculation():
    """Verify accuracy, match rates, and anomaly precision/recall calculations."""
    results = [
        BenchmarkResult(
            test_case_id="TC-1",
            method="test_method",
            metric_id="revenue",
            accession_number="ACC-1",
            company="AAPL",
            expected_value=100.0,
            expected_unit="USD",
            expected_period="2026-09-26",
            expected_concept="Revenues",
            predicted_value=100.0,
            predicted_unit="USD",
            predicted_period="2026-09-26",
            predicted_concept="Revenues",
            has_evidence=True,
            is_value_match=True,
            is_unit_match=True,
            is_period_match=True,
            is_concept_match=True,
        ),
        BenchmarkResult(
            test_case_id="TC-2",
            method="test_method",
            metric_id="net_income",
            accession_number="ACC-1",
            company="AAPL",
            expected_value=50.0,
            expected_unit="USD",
            expected_period="2026-09-26",
            expected_concept="NetIncomeLoss",
            predicted_value=40.0,  # value mismatch
            predicted_unit="USD",
            predicted_period="2026-09-26",
            predicted_concept="NetIncomeLoss",
            has_evidence=True,
            is_value_match=False,
            is_unit_match=True,
            is_period_match=True,
            is_concept_match=True,
        ),
        BenchmarkResult(
            test_case_id="TC-3",
            method="test_method",
            metric_id="gross_profit",
            accession_number="ACC-1",
            company="AAPL",
            expected_value=80.0,
            expected_unit="USD",
            expected_period="2026-09-26",
            expected_concept="GrossProfit",
            predicted_value=None,  # missing
            predicted_unit=None,
            predicted_period=None,
            predicted_concept=None,
            has_evidence=False,
            is_value_match=False,
            is_unit_match=False,
            is_period_match=False,
            is_concept_match=False,
        ),
    ]

    anomaly_flags = {"TC-1": False, "TC-2": True, "TC-3": False}
    metrics = compute_metrics(results, anomaly_flags)

    assert metrics.total_cases == 3
    assert metrics.evaluated_cases == 3
    assert metrics.not_evaluated_cases == 0
    assert metrics.predictions_returned == 2
    assert metrics.exact_matches == 1
    assert metrics.value_matches == 1
    assert metrics.missing_values == 1
    assert metrics.value_mismatches == 1
    assert pytest.approx(metrics.accuracy, 0.01) == 1 / 3
    assert pytest.approx(metrics.value_match_rate, 0.01) == 1 / 3
    assert pytest.approx(metrics.missing_value_rate, 0.01) == 1 / 3
    # Evaluated = 2 (TC-1 and TC-2)
    assert pytest.approx(metrics.unit_accuracy, 0.01) == 1.0
    assert pytest.approx(metrics.period_accuracy, 0.01) == 1.0
    assert pytest.approx(metrics.false_positive_rate, 0.01) == 0.5

    # Anomaly metrics: TC-2 has ref anomaly and predicted mismatch -> TP=1, FP=0, FN=0
    assert metrics.anomaly_true_positives == 1
    assert metrics.anomaly_precision == 1.0
    assert metrics.anomaly_recall == 1.0


def test_evaluator_simple_tag_baseline():
    """Verify Baseline A simple tag lookup produces non-empty results."""
    evaluator = BenchmarkEvaluator()
    records = load_reference_dataset()[:5]
    results = evaluator.evaluate_simple_tag_baseline(records)

    assert len(results) == 5
    for r in results:
        assert r.method == "simple_tag"
        assert r.expected_value > 0
        assert r.test_case_id


def test_evaluator_llm_baseline_disclosure():
    """Verify Baseline B is explicitly not evaluated until implemented."""
    evaluator = BenchmarkEvaluator()
    records = load_reference_dataset()[:3]
    results = evaluator.evaluate_llm_baseline(records)

    assert len(results) == 3
    for r in results:
        assert r.method == "llm_baseline"
        assert r.predicted_value is None
        assert r.error_type == "not_evaluated"
        assert "no LLM baseline execution is implemented" in r.notes


def test_unavailable_baseline_is_not_counted_as_a_failed_prediction():
    result = BenchmarkResult(
        test_case_id="TC-UNAVAILABLE",
        method="regex_simulation",
        metric_id="revenue",
        accession_number="ACC-1",
        company="AAPL",
        expected_value=100.0,
        expected_unit="USD",
        expected_period="2026-09-26",
        expected_concept="Revenues",
        error_type="not_evaluated",
    )

    metrics = compute_metrics([result], {"TC-UNAVAILABLE": False})

    assert metrics.total_cases == 1
    assert metrics.evaluated_cases == 0
    assert metrics.not_evaluated_cases == 1
    assert metrics.missing_values == 0
    assert metrics.accuracy is None
    assert metrics.evidence_support_rate is None


def test_evaluator_filingguard_pipeline():
    """Verify Method C FilingGuard evaluation produces high-accuracy results."""
    evaluator = BenchmarkEvaluator()
    records = load_reference_dataset()
    results = evaluator.evaluate_filingguard_pipeline(records)

    assert len(results) == len(records)
    # Check that AAPL 2026 revenue is an exact match
    aapl_rev = next(r for r in results if r.test_case_id == "REF-AAPL-2026-REV")
    assert aapl_rev.is_value_match is True
    assert aapl_rev.is_period_match is True
    assert aapl_rev.is_unit_match is True
    assert aapl_rev.has_evidence is True


def test_regex_baseline_does_not_use_reference_values_as_predictions():
    results = BenchmarkEvaluator().evaluate_offline_regex_baseline(load_reference_dataset()[:2])

    assert len(results) == 2
    assert all(result.predicted_value is None for result in results)
    assert all(result.error_type == "not_evaluated" for result in results)


def test_filingguard_evidence_requires_matching_locator_and_verified_document(tmp_path):
    ref = load_reference_dataset()[0]
    filing_path = tmp_path / "filing.htm"
    filing_path.write_bytes(b"cached filing bytes")
    document_hash = hashlib.sha256(filing_path.read_bytes()).hexdigest()

    doc_repo = MagicMock()
    doc_repo.get_by_accession.return_value = SimpleNamespace(
        accession_number=ref.accession_number,
        cik=ref.cik,
        source_url=f"https://www.sec.gov/Archives/edgar/data/{ref.cik}/filing.htm",
        local_path=str(filing_path),
        sha256_hash=document_hash,
    )
    evaluator = BenchmarkEvaluator(doc_repo=doc_repo)
    fact = FactRecord(
        cik=ref.cik,
        accession_number=ref.accession_number,
        metric_id=ref.metric_id,
        canonical_name=ref.canonical_name,
        raw_value=ref.expected_value,
        normalized_value=ref.expected_value,
        unit=ref.expected_unit,
        taxonomy="us-gaap",
        concept=ref.expected_concept,
        period_type=ref.period_type,
        period_end=ref.period_end,
        fiscal_year=ref.fiscal_year,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="test fact",
    )
    parsed_fact = ParsedXBRLFact(
        accession_number=ref.accession_number,
        concept_name=ref.expected_concept,
        namespace="us-gaap",
        numeric_value=ref.expected_value,
        unit=ref.expected_unit,
        context_id="ctx",
        period_type=ref.period_type,
        end_date=ref.period_end,
        source_locator="ix:nonfraction#fact-1",
        source_doc_hash=document_hash,
    )

    assert evaluator._has_traceable_evidence(ref, fact, [parsed_fact])[0] is True
    unlinked_fact = parsed_fact.model_copy(update={"source_doc_hash": "different-hash"})
    assert evaluator._has_traceable_evidence(ref, fact, [unlinked_fact])[0] is False


def test_deterministic_reproducibility():
    """Verify executing benchmark repeatedly produces identical deterministic numbers."""
    evaluator = BenchmarkEvaluator()
    records = load_reference_dataset()[:10]

    run1 = evaluator.run_benchmark(records=records, persist=False)
    run2 = evaluator.run_benchmark(records=records, persist=False)

    assert run1["metrics"]["filingguard"]["accuracy"] == run2["metrics"]["filingguard"]["accuracy"]
    assert run1["metrics"]["simple_tag"]["accuracy"] == run2["metrics"]["simple_tag"]["accuracy"]
    assert len(run1["comparison_table"]) == len(run2["comparison_table"])


def test_benchmark_repository_crud():
    """Verify BenchmarkRepository save, get, and clear operations."""
    repo = BenchmarkRepository()
    repo.clear_results(method="unit_test_method")

    sample = [
        BenchmarkResultRecord(
            benchmark_id="BM-TEST-1",
            filing_id="0000320193-26-000026",
            test_case_id="TC-UNIT-1",
            method="unit_test_method",
            metric_name="revenue",
            expected_value=100.0,
            expected_unit="USD",
            expected_period="2026-09-26",
            predicted_value=100.0,
            predicted_unit="USD",
            predicted_period="2026-09-26",
            result="PASS",
            reviewer_reference="SEC Filing",
        )
    ]
    repo.save_results(sample)
    fetched = repo.get_results(method="unit_test_method")
    assert len(fetched) == 1
    assert fetched[0].test_case_id == "TC-UNIT-1"
    assert fetched[0].result == "PASS"

    repo.clear_results(method="unit_test_method")
    assert len(repo.get_results(method="unit_test_method")) == 0



def test_benchmark_52_facts_expanded():
    """BEN-01 Test: Reference dataset contains exactly 52 verified facts across 6 companies."""
    records = load_reference_dataset()
    assert len(records) == 52
    companies = {r.ticker for r in records}
    assert companies == {"AAPL", "MSFT", "AMZN", "WMT", "XOM", "TSLA"}
    assert all(r.reviewer_verified for r in records)


def test_offline_regex_baseline_is_not_evaluated():
    """Baseline C must not report scores until an independent extractor exists."""
    evaluator = BenchmarkEvaluator()
    records = load_reference_dataset()[:6]
    results = evaluator.evaluate_offline_regex_baseline(records)
    assert len(results) == 6
    assert all(r.method == "regex_simulation" for r in results)
    assert all(r.error_type == "not_evaluated" for r in results)
    assert all(r.predicted_value is None for r in results)


def test_evaluator_runs_all_four_methods():
    """BEN-01 Test: Full benchmark runs across simple_tag, llm_baseline, regex_simulation, and filingguard."""
    evaluator = BenchmarkEvaluator()
    records = load_reference_dataset()[:10]
    res = evaluator.run_benchmark(records=records, persist=False)
    metrics = res["metrics"]
    assert "simple_tag" in metrics
    assert "llm_baseline" in metrics
    assert "regex_simulation" in metrics
    assert "filingguard" in metrics
    assert len(res["comparison_table"]) == 10
