import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.scoring")


class MetricConfidenceRecord(BaseModel):
    id: Optional[int] = None
    accession_number: str
    cik: str
    metric_id: str
    canonical_name: str
    confidence_score: float  # 0.0 to 1.0
    quality_score_100: float  # 0.0 to 100.0
    status: str  # 'HIGH', 'MEDIUM', 'LOW'
    review_category: str  # 'AUTO_PASS', 'REVIEW_RECOMMENDED', 'MANDATORY_REVIEW'
    factors: Dict[str, float]
    positive_factors: List[str]
    negative_factors: List[str]
    evidence_references: Dict[str, Any]
    explanation: str
    review_recommendations: List[str]
    version: str = "1.0.0"
    created_at: Optional[str] = None


class FilingConfidenceRecord(BaseModel):
    accession_number: str
    cik: str
    overall_score: float  # 0.0 to 1.0
    quality_score_100: float  # 0.0 to 100.0
    overall_status: str  # 'HIGH', 'MEDIUM', 'LOW'
    overall_review_category: str  # 'AUTO_PASS', 'REVIEW_RECOMMENDED', 'MANDATORY_REVIEW'
    metrics_assessed_count: int
    metrics_missing_count: int
    critical_metrics_present: bool = True
    score_factors: Dict[str, float]
    reduction_reasons: List[str]
    summary_explanation: str
    version: str = "1.0.0"
    created_at: Optional[str] = None


class ScoringRepository:
    """Repository for managing metric-level and filing-level confidence scores."""

    def save_metric_scores(self, records: List[MetricConfidenceRecord]) -> None:
        """Batch save metric confidence scores with clean replacement for the accession."""
        if not records:
            return

        accession_number = records[0].accession_number
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM metric_confidence_scores WHERE accession_number = ?;",
                (accession_number,),
            )

            insert_sql = """
            INSERT INTO metric_confidence_scores (
                accession_number, cik, metric_id, canonical_name,
                confidence_score, quality_score_100, status, review_category,
                factors_json, positive_factors_json, negative_factors_json,
                evidence_refs_json, explanation, review_recommendations_json, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """

            for r in records:
                cursor.execute(
                    insert_sql,
                    (
                        r.accession_number,
                        r.cik,
                        r.metric_id,
                        r.canonical_name,
                        float(r.confidence_score),
                        float(r.quality_score_100),
                        r.status,
                        r.review_category,
                        json.dumps(r.factors),
                        json.dumps(r.positive_factors),
                        json.dumps(r.negative_factors),
                        json.dumps(r.evidence_references),
                        r.explanation,
                        json.dumps(r.review_recommendations),
                        r.version,
                    ),
                )
        logger.info(
            f"Saved {len(records)} metric confidence score records for accession {accession_number}."
        )

    def get_metric_scores_by_accession(self, accession_number: str) -> List[MetricConfidenceRecord]:
        """Fetch all scored metrics for a filing accession."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, accession_number, cik, metric_id, canonical_name,
                       confidence_score, quality_score_100, status, review_category,
                       factors_json, positive_factors_json, negative_factors_json,
                       evidence_refs_json, explanation, review_recommendations_json,
                       version, created_at
                FROM metric_confidence_scores
                WHERE accession_number = ?
                ORDER BY id ASC;
                """,
                (accession_number,),
            )
            rows = cursor.fetchall()

        results: List[MetricConfidenceRecord] = []
        for row in rows:
            results.append(
                MetricConfidenceRecord(
                    id=row["id"],
                    accession_number=row["accession_number"],
                    cik=row["cik"],
                    metric_id=row["metric_id"],
                    canonical_name=row["canonical_name"],
                    confidence_score=row["confidence_score"],
                    quality_score_100=row["quality_score_100"],
                    status=row["status"],
                    review_category=row["review_category"],
                    factors=json.loads(row["factors_json"]),
                    positive_factors=json.loads(row["positive_factors_json"]),
                    negative_factors=json.loads(row["negative_factors_json"]),
                    evidence_references=json.loads(row["evidence_refs_json"]),
                    explanation=row["explanation"],
                    review_recommendations=json.loads(row["review_recommendations_json"]),
                    version=row["version"],
                    created_at=row["created_at"],
                )
            )
        return results

    def get_metric_score(self, accession_number: str, metric_id: str) -> Optional[MetricConfidenceRecord]:
        """Fetch confidence score for a specific metric within a filing."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, accession_number, cik, metric_id, canonical_name,
                       confidence_score, quality_score_100, status, review_category,
                       factors_json, positive_factors_json, negative_factors_json,
                       evidence_refs_json, explanation, review_recommendations_json,
                       version, created_at
                FROM metric_confidence_scores
                WHERE accession_number = ? AND metric_id = ?;
                """,
                (accession_number, metric_id),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return MetricConfidenceRecord(
            id=row["id"],
            accession_number=row["accession_number"],
            cik=row["cik"],
            metric_id=row["metric_id"],
            canonical_name=row["canonical_name"],
            confidence_score=row["confidence_score"],
            quality_score_100=row["quality_score_100"],
            status=row["status"],
            review_category=row["review_category"],
            factors=json.loads(row["factors_json"]),
            positive_factors=json.loads(row["positive_factors_json"]),
            negative_factors=json.loads(row["negative_factors_json"]),
            evidence_references=json.loads(row["evidence_refs_json"]),
            explanation=row["explanation"],
            review_recommendations=json.loads(row["review_recommendations_json"]),
            version=row["version"],
            created_at=row["created_at"],
        )

    def save_filing_score(self, record: FilingConfidenceRecord) -> None:
        """Upsert overall filing confidence score."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            upsert_sql = """
            INSERT OR REPLACE INTO filing_confidence_scores (
                accession_number, cik, overall_score, quality_score_100,
                overall_status, overall_review_category,
                metrics_assessed_count, metrics_missing_count,
                critical_metrics_present, score_factors_json,
                reduction_reasons_json, summary_explanation, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            cursor.execute(
                upsert_sql,
                (
                    record.accession_number,
                    record.cik,
                    float(record.overall_score),
                    float(record.quality_score_100),
                    record.overall_status,
                    record.overall_review_category,
                    record.metrics_assessed_count,
                    record.metrics_missing_count,
                    1 if record.critical_metrics_present else 0,
                    json.dumps(record.score_factors),
                    json.dumps(record.reduction_reasons),
                    record.summary_explanation,
                    record.version,
                ),
            )
        logger.info(f"Saved filing confidence score for accession {record.accession_number}.")

    def get_filing_score(self, accession_number: str) -> Optional[FilingConfidenceRecord]:
        """Fetch filing-level confidence score."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT accession_number, cik, overall_score, quality_score_100,
                       overall_status, overall_review_category,
                       metrics_assessed_count, metrics_missing_count,
                       critical_metrics_present, score_factors_json,
                       reduction_reasons_json, summary_explanation, version, created_at
                FROM filing_confidence_scores
                WHERE accession_number = ?;
                """,
                (accession_number,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return FilingConfidenceRecord(
            accession_number=row["accession_number"],
            cik=row["cik"],
            overall_score=row["overall_score"],
            quality_score_100=row["quality_score_100"],
            overall_status=row["overall_status"],
            overall_review_category=row["overall_review_category"],
            metrics_assessed_count=row["metrics_assessed_count"],
            metrics_missing_count=row["metrics_missing_count"],
            critical_metrics_present=bool(row["critical_metrics_present"]),
            score_factors=json.loads(row["score_factors_json"]),
            reduction_reasons=json.loads(row["reduction_reasons_json"]),
            summary_explanation=row["summary_explanation"],
            version=row["version"],
            created_at=row["created_at"],
        )

