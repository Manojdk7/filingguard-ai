"""
CLI script to execute the Phase 11 accuracy and baseline benchmark.
Usage: python scripts/run_benchmark.py [--persist]
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.benchmark.evaluator import BenchmarkEvaluator


def main():
    parser = argparse.ArgumentParser(description="Execute FilingGuard AI benchmark against reference facts.")
    parser.add_argument("--persist", action="store_true", help="Persist results to SQLite benchmark_results table.")
    args = parser.parse_args()

    evaluator = BenchmarkEvaluator()
    print("Executing benchmark against verified SEC reference facts...")
    report = evaluator.run_benchmark(persist=args.persist)

    summary = report["reference_summary"]
    metrics = report["metrics"]

    print("\n" + "=" * 65)
    print(" FILINGGUARD AI — BENCHMARK ACCURACY REPORT")
    print("=" * 65)
    print(f"Total Reference Facts: {summary['total_reference_facts']}")
    print(f"Companies:             {', '.join(summary['companies'])} ({summary['company_count']} companies)")
    print(f"Filings Covered:       {summary['filing_count']}")
    print(f"Metrics Covered:       {summary['metric_coverage_count']} canonical metrics")
    print("-" * 65)

    headers = f"{'Method':<25} | {'Accuracy':<10} | {'Value Match':<12} | {'Evidence':<10}"
    print(headers)
    print("-" * 65)

    for m_key, label in [("simple_tag", "Baseline A: Simple Tag"), ("llm_baseline", "Baseline B: LLM"), ("filingguard", "FilingGuard Hybrid")]:
        m = metrics[m_key]
        acc_str = f"{m['accuracy'] * 100:.1f}%" if m['total_cases'] else "N/A"
        val_str = f"{m['value_match_rate'] * 100:.1f}%" if m['total_cases'] else "N/A"
        ev_str = f"{m['evidence_support_rate'] * 100:.1f}%" if m['total_cases'] else "N/A"
        print(f"{label:<25} | {acc_str:<10} | {val_str:<12} | {ev_str:<10}")

    print("=" * 65)
    print(f"Persistence: {'Saved to SQLite' if args.persist else 'Dry-run (not saved)'}")


if __name__ == "__main__":
    main()

