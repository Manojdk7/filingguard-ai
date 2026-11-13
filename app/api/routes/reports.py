"""
API routes for Phase 11 Benchmark and Verification Reports.
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.api.schemas.benchmark import (
    BenchmarkReportResponse,
    BenchmarkResultItemSchema,
    ComparisonRowSchema,
    MethodMetricsSchema,
    ReferenceSummarySchema,
)
from app.benchmark.evaluator import BenchmarkEvaluator
from app.database.repositories.benchmark_repository import BenchmarkRepository

logger = logging.getLogger("filingguard.api.routes.reports")

router = APIRouter(prefix="/benchmark", tags=["Benchmark & Accuracy Reports"])

_evaluator = BenchmarkEvaluator()
_bench_repo = BenchmarkRepository()


@router.get("/report", response_model=BenchmarkReportResponse)
def get_benchmark_report(run_fresh: bool = Query(False, description="Force re-running the benchmark")):
    """Retrieve full benchmark report comparing Baseline A, Baseline B, and FilingGuard."""
    try:
        report = _evaluator.run_benchmark(persist=run_fresh)
        return report
    except Exception as e:
        logger.error(f"Failed to generate benchmark report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate benchmark report: {str(e)}")


@router.get("/summary")
def get_benchmark_summary():
    """Retrieve summary metrics and accuracy rates across all benchmark methods."""
    try:
        report = _evaluator.run_benchmark(persist=False)
        return {
            "reference_summary": report["reference_summary"],
            "metrics": report["metrics"],
            "limitations": report["limitations"],
        }
    except Exception as e:
        logger.error(f"Failed to retrieve benchmark summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary: {str(e)}")


@router.get("/results", response_model=List[BenchmarkResultItemSchema])
def get_benchmark_results(
    method: Optional[str] = Query(None, description="Filter by method: simple_tag, llm_baseline, filingguard"),
):
    """Retrieve itemized results for reference facts evaluated against benchmark methods."""
    try:
        report = _evaluator.run_benchmark(persist=False)
        all_results = report["detailed_results"]
        if method:
            if method not in all_results:
                raise HTTPException(status_code=400, detail=f"Invalid method: {method}. Must be one of {list(all_results.keys())}")
            return all_results[method]

        combined = []
        for m_results in all_results.values():
            combined.extend(m_results)
        return combined
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve benchmark results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve results: {str(e)}")


@router.get("/comparison", response_model=List[ComparisonRowSchema])
def get_benchmark_comparison():
    """Retrieve row-by-row comparison table across methods for all reference test cases."""
    try:
        report = _evaluator.run_benchmark(persist=False)
        return report["comparison_table"]
    except Exception as e:
        logger.error(f"Failed to retrieve benchmark comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve comparison: {str(e)}")


@router.post("/run", response_model=BenchmarkReportResponse)
def run_and_persist_benchmark():
    """Trigger a benchmark run and persist all results to the database."""
    try:
        report = _evaluator.run_benchmark(persist=True)
        return report
    except Exception as e:
        logger.error(f"Failed to run and persist benchmark: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Benchmark execution failed: {str(e)}")

