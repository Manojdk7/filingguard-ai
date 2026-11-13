import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.reconciliation")


class ReconciliationRecord(BaseModel):
    id: Optional[int] = None
    accession_number: str
    cik: str
    metric_id: str
    canonical_name: str
    status: str
    company_facts_value: Optional[float] = None
    ixbrl_value: Optional[float] = None
    difference: Optional[float] = None
    company_facts_concept: Optional[str] = None
    ixbrl_concept: Optional[str] = None
    company_facts_unit: Optional[str] = None
    ixbrl_unit: Optional[str] = None
    company_facts_period: Optional[str] = None
    ixbrl_period: Optional[str] = None
    is_segment_mismatch: bool = False
    explanation: str
    created_at: Optional[str] = None


class CustomConceptCandidateRecord(BaseModel):
    id: Optional[int] = None
    accession_number: str
    custom_concept: str
    namespace: str
    candidate_metric_id: Optional[str] = None
    candidate_metric_name: Optional[str] = None
    confidence_level: str  # 'candidate_for_review', 'unresolved'
    reason: str
    is_reviewed: bool = False
    created_at: Optional[str] = None


class ReconciliationRepository:
    """Repository for storing and querying cross-source reconciliations and custom concept reviews."""

    def save_reconciliations(self, records: List[ReconciliationRecord]) -> None:
        """Batch insert reconciliation outcomes."""
        if not records:
            return

        sql = """
        INSERT INTO cross_source_reconciliations (
            accession_number, cik, metric_id, canonical_name, status,
            company_facts_value, ixbrl_value, difference,
            company_facts_concept, ixbrl_concept, company_facts_unit,
            ixbrl_unit, company_facts_period, ixbrl_period,
            is_segment_mismatch, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for r in records:
                cursor.execute(sql, (
                    r.accession_number,
                    r.cik,
                    r.metric_id,
                    r.canonical_name,
                    r.status,
                    r.company_facts_value,
                    r.ixbrl_value,
                    r.difference,
                    r.company_facts_concept,
                    r.ixbrl_concept,
                    r.company_facts_unit,
                    r.ixbrl_unit,
                    r.company_facts_period,
                    r.ixbrl_period,
                    1 if r.is_segment_mismatch else 0,
                    r.explanation,
                ))
        logger.debug(f"Saved {len(records)} reconciliation records for accession {records[0].accession_number}")

    def delete_reconciliations_by_accession(self, accession_number: str) -> None:
        """Idempotently clear previous reconciliations for an accession."""
        sql = "DELETE FROM cross_source_reconciliations WHERE accession_number = ?;"
        with get_db_connection() as conn:
            conn.execute(sql, (accession_number,))

    def get_reconciliations_by_accession(self, accession_number: str) -> List[ReconciliationRecord]:
        """Query reconciliation records by accession number."""
        sql = (
            "SELECT * FROM cross_source_reconciliations "
            "WHERE accession_number = ? ORDER BY metric_id ASC, id ASC;"
        )
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number,))
            rows = cursor.fetchall()
            return [
                ReconciliationRecord(
                    id=r["id"],
                    accession_number=r["accession_number"],
                    cik=r["cik"],
                    metric_id=r["metric_id"],
                    canonical_name=r["canonical_name"],
                    status=r["status"],
                    company_facts_value=r["company_facts_value"],
                    ixbrl_value=r["ixbrl_value"],
                    difference=r["difference"],
                    company_facts_concept=r["company_facts_concept"],
                    ixbrl_concept=r["ixbrl_concept"],
                    company_facts_unit=r["company_facts_unit"],
                    ixbrl_unit=r["ixbrl_unit"],
                    company_facts_period=r["company_facts_period"],
                    ixbrl_period=r["ixbrl_period"],
                    is_segment_mismatch=bool(r["is_segment_mismatch"]),
                    explanation=r["explanation"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def save_custom_candidates(self, records: List[CustomConceptCandidateRecord]) -> None:
        """Persist potential custom concepts identified for human reviewer consideration."""
        if not records:
            return

        sql = """
        INSERT INTO custom_concept_candidates (
            accession_number, custom_concept, namespace,
            candidate_metric_id, candidate_metric_name,
            confidence_level, reason, is_reviewed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for r in records:
                cursor.execute(sql, (
                    r.accession_number,
                    r.custom_concept,
                    r.namespace,
                    r.candidate_metric_id,
                    r.candidate_metric_name,
                    r.confidence_level,
                    r.reason,
                    1 if r.is_reviewed else 0,
                ))

    def delete_custom_candidates_by_accession(self, accession_number: str) -> None:
        """Clear custom candidates for accession."""
        sql = "DELETE FROM custom_concept_candidates WHERE accession_number = ?;"
        with get_db_connection() as conn:
            conn.execute(sql, (accession_number,))

    def get_custom_candidates_by_accession(self, accession_number: str) -> List[CustomConceptCandidateRecord]:
        sql = "SELECT * FROM custom_concept_candidates WHERE accession_number = ? ORDER BY id ASC;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number,))
            rows = cursor.fetchall()
            return [
                CustomConceptCandidateRecord(
                    id=r["id"],
                    accession_number=r["accession_number"],
                    custom_concept=r["custom_concept"],
                    namespace=r["namespace"],
                    candidate_metric_id=r["candidate_metric_id"],
                    candidate_metric_name=r["candidate_metric_name"],
                    confidence_level=r["confidence_level"],
                    reason=r["reason"],
                    is_reviewed=bool(r["is_reviewed"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]
