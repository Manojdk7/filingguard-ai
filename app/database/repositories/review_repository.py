import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.review")


class ReviewRecord(BaseModel):
    id: Optional[int] = None
    review_id: str
    accession_number: str
    thread_id: Optional[str] = None
    metric_id: Optional[str] = None
    canonical_name: Optional[str] = None
    review_round: int = 1
    reviewer_id: str
    decision: str  # 'APPROVED', 'CORRECTED', 'REJECTED'
    original_value: Optional[float] = None
    corrected_value: Optional[float] = None
    unit: Optional[str] = None
    comment: str
    evidence_used: Optional[str] = None
    idempotency_key: Optional[str] = None
    previous_validation_status: Optional[str] = None
    new_validation_status: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: Optional[str] = None


class ReviewRepository:
    """Repository for managing human auditor review decisions and corrections."""

    def save_review(self, review: ReviewRecord) -> ReviewRecord:
        """Persist a human review record."""
        sql = """
        INSERT INTO human_reviews (
            review_id, accession_number, thread_id, metric_id, canonical_name,
            review_round, reviewer_id, decision, original_value, corrected_value,
            unit, comment, evidence_used, idempotency_key,
            previous_validation_status, new_validation_status, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    review.review_id,
                    review.accession_number,
                    review.thread_id,
                    review.metric_id,
                    review.canonical_name,
                    review.review_round,
                    review.reviewer_id,
                    review.decision.upper(),
                    review.original_value,
                    review.corrected_value,
                    review.unit,
                    review.comment,
                    review.evidence_used,
                    review.idempotency_key,
                    review.previous_validation_status,
                    review.new_validation_status,
                    review.metadata_json or "{}",
                ),
            )
            review.id = cursor.lastrowid
        logger.info(
            f"Saved review {review.review_id} for {review.accession_number} "
            f"[{review.metric_id or 'FILING'}] by {review.reviewer_id}: {review.decision}"
        )
        return review

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ReviewRecord]:
        """Retrieve review record by idempotency key."""
        if not idempotency_key:
            return None
        sql = "SELECT * FROM human_reviews WHERE idempotency_key = ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (idempotency_key,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_by_review_id(self, review_id: str) -> Optional[ReviewRecord]:
        """Retrieve review record by unique review ID."""
        sql = "SELECT * FROM human_reviews WHERE review_id = ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (review_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def delete_review(self, review_id: str) -> None:
        """Delete review record (used for rollback if audit recording fails)."""
        sql = "DELETE FROM human_reviews WHERE review_id = ?;"
        with get_db_connection() as conn:
            conn.execute(sql, (review_id,))
        logger.info(f"Deleted review {review_id} for rollback/cleanup.")

    def get_reviews_by_accession(self, accession_number: str) -> List[ReviewRecord]:
        """Fetch all review records for a filing ordered by round and timestamp."""
        sql = """
        SELECT * FROM human_reviews 
        WHERE accession_number = ? 
        ORDER BY review_round ASC, created_at ASC;
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number,))
            rows = cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_reviews_by_metric(self, accession_number: str, metric_id: str) -> List[ReviewRecord]:
        """Fetch all review records for a specific metric within an accession."""
        sql = """
        SELECT * FROM human_reviews 
        WHERE accession_number = ? AND metric_id = ? 
        ORDER BY review_round ASC, created_at ASC;
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number, metric_id))
            rows = cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_latest_review_round(self, accession_number: str, metric_id: Optional[str] = None) -> int:
        """Determine latest review round for an accession and optional metric."""
        if metric_id:
            sql = "SELECT MAX(review_round) as max_round FROM human_reviews WHERE accession_number = ? AND metric_id = ?;"
            params = (accession_number, metric_id)
        else:
            sql = "SELECT MAX(review_round) as max_round FROM human_reviews WHERE accession_number = ?;"
            params = (accession_number,)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row and row["max_round"] is not None:
                return int(row["max_round"])
            return 0

    def _row_to_record(self, row: Any) -> ReviewRecord:
        return ReviewRecord(
            id=row["id"],
            review_id=row["review_id"],
            accession_number=row["accession_number"],
            thread_id=row["thread_id"],
            metric_id=row["metric_id"],
            canonical_name=row["canonical_name"],
            review_round=row["review_round"],
            reviewer_id=row["reviewer_id"],
            decision=row["decision"],
            original_value=row["original_value"],
            corrected_value=row["corrected_value"],
            unit=row["unit"],
            comment=row["comment"],
            evidence_used=row["evidence_used"],
            idempotency_key=row["idempotency_key"],
            previous_validation_status=row["previous_validation_status"],
            new_validation_status=row["new_validation_status"],
            metadata_json=row["metadata_json"],
            created_at=row["created_at"],
        )

