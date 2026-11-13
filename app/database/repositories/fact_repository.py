import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.fact")


class FactRecord(BaseModel):
    id: Optional[int] = None
    cik: str
    accession_number: str
    metric_id: str
    canonical_name: str
    raw_value: float
    normalized_value: float
    unit: str
    taxonomy: str
    concept: str
    period_type: str
    period_start: Optional[str] = None
    period_end: str
    fiscal_year: int
    fiscal_period: str
    form: str
    filed_date: Optional[str] = None
    frame: Optional[str] = None
    status: str  # 'selected', 'ambiguous', 'candidate', 'rejected'
    selection_explanation: str
    created_at: Optional[str] = None


class FactRepository:
    """Repository for persisting and querying extracted company facts."""

    def save_facts(self, facts: List[FactRecord]) -> None:
        """Persist a batch of fact records."""
        if not facts:
            return

        sql = """
        INSERT INTO company_facts (
            cik, accession_number, metric_id, canonical_name,
            raw_value, normalized_value, unit, taxonomy, concept,
            period_type, period_start, period_end, fiscal_year,
            fiscal_period, form, filed_date, frame, status,
            selection_explanation
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for f in facts:
                cursor.execute(sql, (
                    f.cik,
                    f.accession_number,
                    f.metric_id,
                    f.canonical_name,
                    f.raw_value,
                    f.normalized_value,
                    f.unit,
                    f.taxonomy,
                    f.concept,
                    f.period_type,
                    f.period_start,
                    f.period_end,
                    f.fiscal_year,
                    f.fiscal_period,
                    f.form,
                    f.filed_date,
                    f.frame,
                    f.status,
                    f.selection_explanation,
                ))
        logger.debug(f"Saved {len(facts)} fact records for accession {facts[0].accession_number}")

    def get_selected_facts_by_accession(self, accession_number: str) -> List[FactRecord]:
        """Fetch all selected primary facts for a specific filing accession."""
        sql = """
        SELECT * FROM company_facts
        WHERE accession_number = ? AND status = 'selected'
        ORDER BY metric_id ASC;
        """
        return self._fetch_facts(sql, (accession_number,))

    def get_all_facts_by_accession(self, accession_number: str) -> List[FactRecord]:
        """Fetch all facts (candidates, selected, rejected) for a specific filing accession."""
        sql = """
        SELECT * FROM company_facts
        WHERE accession_number = ?
        ORDER BY metric_id ASC, id ASC;
        """
        return self._fetch_facts(sql, (accession_number,))

    def delete_facts_by_accession(self, accession_number: str) -> None:
        """Clear existing facts for a filing to permit clean, idempotent re-extraction."""
        sql = "DELETE FROM company_facts WHERE accession_number = ?;"
        with get_db_connection() as conn:
            conn.execute(sql, (accession_number,))

    def _fetch_facts(self, sql: str, params: tuple) -> List[FactRecord]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [
                FactRecord(
                    id=r["id"],
                    cik=r["cik"],
                    accession_number=r["accession_number"],
                    metric_id=r["metric_id"],
                    canonical_name=r["canonical_name"],
                    raw_value=r["raw_value"],
                    normalized_value=r["normalized_value"],
                    unit=r["unit"],
                    taxonomy=r["taxonomy"],
                    concept=r["concept"],
                    period_type=r["period_type"],
                    period_start=r["period_start"],
                    period_end=r["period_end"],
                    fiscal_year=r["fiscal_year"],
                    fiscal_period=r["fiscal_period"],
                    form=r["form"],
                    filed_date=r["filed_date"],
                    frame=r["frame"],
                    status=r["status"],
                    selection_explanation=r["selection_explanation"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

