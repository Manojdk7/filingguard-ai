import logging
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.benchmark")


class BenchmarkResultRecord(BaseModel):
    id: Optional[int] = None
    benchmark_id: str
    filing_id: str
    test_case_id: str
    method: str
    metric_name: str
    expected_value: Optional[float] = None
    expected_unit: Optional[str] = None
    expected_period: Optional[str] = None
    predicted_value: Optional[float] = None
    predicted_unit: Optional[str] = None
    predicted_period: Optional[str] = None
    result: str  # 'PASS', 'FAIL', 'MISSING', 'SKIPPED'
    reviewer_reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


class BenchmarkRepository:
    """Repository for persisting and retrieving benchmark evaluation results."""

    def save_results(self, records: List[BenchmarkResultRecord]) -> None:
        """Persist a batch of benchmark results."""
        if not records:
            return

        sql = """
        INSERT INTO benchmark_results (
            benchmark_id, filing_id, test_case_id, method, metric_name,
            expected_value, expected_unit, expected_period,
            predicted_value, predicted_unit, predicted_period,
            result, reviewer_reference, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for r in records:
                cursor.execute(sql, (
                    r.benchmark_id,
                    r.filing_id,
                    r.test_case_id,
                    r.method,
                    r.metric_name,
                    r.expected_value,
                    r.expected_unit,
                    r.expected_period,
                    r.predicted_value,
                    r.predicted_unit,
                    r.predicted_period,
                    r.result,
                    r.reviewer_reference,
                    r.notes,
                ))
        logger.debug(f"Saved {len(records)} benchmark results")

    def get_results(
        self,
        method: Optional[str] = None,
        filing_id: Optional[str] = None,
    ) -> List[BenchmarkResultRecord]:
        """Fetch benchmark results, optionally filtered by method or filing_id."""
        query = "SELECT * FROM benchmark_results WHERE 1=1"
        params: List[Any] = []
        if method:
            query += " AND method = ?"
            params.append(method)
        if filing_id:
            query += " AND filing_id = ?"
            params.append(filing_id)
        query += " ORDER BY id ASC;"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [
                BenchmarkResultRecord(
                    id=r["id"],
                    benchmark_id=r["benchmark_id"],
                    filing_id=r["filing_id"],
                    test_case_id=r["test_case_id"],
                    method=r["method"],
                    metric_name=r["metric_name"],
                    expected_value=r["expected_value"],
                    expected_unit=r["expected_unit"],
                    expected_period=r["expected_period"],
                    predicted_value=r["predicted_value"],
                    predicted_unit=r["predicted_unit"],
                    predicted_period=r["predicted_period"],
                    result=r["result"],
                    reviewer_reference=r["reviewer_reference"],
                    notes=r["notes"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def clear_results(self, method: Optional[str] = None) -> None:
        """Clear benchmark results, optionally for a specific method."""
        with get_db_connection() as conn:
            if method:
                conn.execute("DELETE FROM benchmark_results WHERE method = ?;", (method,))
            else:
                conn.execute("DELETE FROM benchmark_results;")

