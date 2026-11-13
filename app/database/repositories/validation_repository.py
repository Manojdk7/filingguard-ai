import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.validation")


class ValidationRecord(BaseModel):
    id: Optional[int] = None
    accession_number: str
    cik: str
    rule_id: str
    rule_name: str
    rule_version: str = "1.0.0"
    validation_category: str  # 'balance_sheet', 'income_statement', 'variance', 'cross_statement'
    status: str  # 'PASS', 'FAIL', 'WARNING', 'NOT_EVALUATED'
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    absolute_difference: Optional[float] = None
    relative_difference: Optional[float] = None
    configured_tolerance: Optional[float] = None
    input_metrics: Dict[str, Any]
    evidence_references: Dict[str, Any]
    explanation: str
    failure_reason: Optional[str] = None
    recommendation: Optional[str] = None
    created_at: Optional[str] = None


class ValidationRepository:
    """Repository for managing financial statement validation results."""

    def save_validations(self, records: List[ValidationRecord]) -> None:
        """Save a batch of validation records with idempotent replacement for the accession."""
        if not records:
            return

        accession_number = records[0].accession_number
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM financial_validations WHERE accession_number = ?;",
                (accession_number,),
            )

            insert_sql = """
            INSERT INTO financial_validations (
                accession_number, cik, rule_id, rule_name, rule_version,
                validation_category, status, expected_value, actual_value,
                absolute_difference, relative_difference, configured_tolerance,
                input_metrics_json, evidence_refs_json, explanation,
                failure_reason, recommendation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """

            for r in records:
                cursor.execute(
                    insert_sql,
                    (
                        r.accession_number,
                        r.cik,
                        r.rule_id,
                        r.rule_name,
                        r.rule_version,
                        r.validation_category,
                        r.status,
                        float(r.expected_value) if r.expected_value is not None else None,
                        float(r.actual_value) if r.actual_value is not None else None,
                        float(r.absolute_difference) if r.absolute_difference is not None else None,
                        float(r.relative_difference) if r.relative_difference is not None else None,
                        float(r.configured_tolerance) if r.configured_tolerance is not None else None,
                        json.dumps(r.input_metrics),
                        json.dumps(r.evidence_references),
                        r.explanation,
                        r.failure_reason,
                        r.recommendation,
                    ),
                )
        logger.info(
            f"Saved {len(records)} financial validation records for accession {accession_number}."
        )

    def get_validations_by_accession(self, accession_number: str) -> List[ValidationRecord]:
        """Fetch all validation results for a filing accession."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, accession_number, cik, rule_id, rule_name, rule_version,
                       validation_category, status, expected_value, actual_value,
                       absolute_difference, relative_difference, configured_tolerance,
                       input_metrics_json, evidence_refs_json, explanation,
                       failure_reason, recommendation, created_at
                FROM financial_validations
                WHERE accession_number = ?
                ORDER BY id ASC;
                """,
                (accession_number,),
            )
            rows = cursor.fetchall()

        results: List[ValidationRecord] = []
        for r in rows:
            results.append(
                ValidationRecord(
                    id=r["id"],
                    accession_number=r["accession_number"],
                    cik=r["cik"],
                    rule_id=r["rule_id"],
                    rule_name=r["rule_name"],
                    rule_version=r["rule_version"],
                    validation_category=r["validation_category"],
                    status=r["status"],
                    expected_value=r["expected_value"],
                    actual_value=r["actual_value"],
                    absolute_difference=r["absolute_difference"],
                    relative_difference=r["relative_difference"],
                    configured_tolerance=r["configured_tolerance"],
                    input_metrics=json.loads(r["input_metrics_json"]),
                    evidence_references=json.loads(r["evidence_refs_json"]),
                    explanation=r["explanation"],
                    failure_reason=r["failure_reason"],
                    recommendation=r["recommendation"],
                    created_at=r["created_at"],
                )
            )
        return results

    def get_validation(self, accession_number: str, rule_id: str) -> Optional[ValidationRecord]:
        """Fetch a specific validation result by accession and rule_id."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, accession_number, cik, rule_id, rule_name, rule_version,
                       validation_category, status, expected_value, actual_value,
                       absolute_difference, relative_difference, configured_tolerance,
                       input_metrics_json, evidence_refs_json, explanation,
                       failure_reason, recommendation, created_at
                FROM financial_validations
                WHERE accession_number = ? AND rule_id = ?;
                """,
                (accession_number, rule_id),
            )
            r = cursor.fetchone()

        if not r:
            return None

        return ValidationRecord(
            id=r["id"],
            accession_number=r["accession_number"],
            cik=r["cik"],
            rule_id=r["rule_id"],
            rule_name=r["rule_name"],
            rule_version=r["rule_version"],
            validation_category=r["validation_category"],
            status=r["status"],
            expected_value=r["expected_value"],
            actual_value=r["actual_value"],
            absolute_difference=r["absolute_difference"],
            relative_difference=r["relative_difference"],
            configured_tolerance=r["configured_tolerance"],
            input_metrics=json.loads(r["input_metrics_json"]),
            evidence_references=json.loads(r["evidence_refs_json"]),
            explanation=r["explanation"],
            failure_reason=r["failure_reason"],
            recommendation=r["recommendation"],
            created_at=r["created_at"],
        )

    def get_validation_summary(self, accession_number: str) -> Dict[str, Any]:
        """Return counts of validations grouped by status."""
        validations = self.get_validations_by_accession(accession_number)
        summary = {
            "total_rules": len(validations),
            "passed": len([v for v in validations if v.status == "PASS"]),
            "failed": len([v for v in validations if v.status == "FAIL"]),
            "warnings": len([v for v in validations if v.status == "WARNING"]),
            "not_evaluated": len([v for v in validations if v.status == "NOT_EVALUATED"]),
        }
        return summary

