import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.xbrl_fact")


class ParsedXBRLFact(BaseModel):
    id: Optional[int] = None
    accession_number: str
    concept_name: str
    namespace: str
    is_custom: bool = False
    value: Optional[str] = None
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    context_id: str
    period_type: str  # 'instant' or 'duration'
    start_date: Optional[str] = None
    end_date: str
    is_segment: bool = False
    dimensions: Dict[str, str] = {}
    source_locator: Optional[str] = None
    source_doc_hash: Optional[str] = None
    source_url: Optional[str] = None
    created_at: Optional[str] = None


class XBRLFactRepository:
    """Repository for storing and querying parsed XBRL/iXBRL facts and dimensions."""

    def save_facts(self, facts: List[ParsedXBRLFact]) -> None:
        """Batch persist parsed XBRL facts."""
        if not facts:
            return

        sql = """
        INSERT INTO xbrl_parsed_facts (
            accession_number, concept_name, namespace, is_custom,
            value, numeric_value, unit, context_id, period_type,
            start_date, end_date, is_segment, dimensions_json,
            source_locator, source_doc_hash, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for f in facts:
                cursor.execute(sql, (
                    f.accession_number,
                    f.concept_name,
                    f.namespace,
                    1 if f.is_custom else 0,
                    f.value,
                    f.numeric_value,
                    f.unit,
                    f.context_id,
                    f.period_type,
                    f.start_date,
                    f.end_date,
                    1 if f.is_segment else 0,
                    json.dumps(f.dimensions or {}, ensure_ascii=False),
                    f.source_locator,
                    f.source_doc_hash,
                    f.source_url,
                ))
        logger.debug(f"Saved {len(facts)} parsed XBRL facts for accession {facts[0].accession_number}")

    def delete_facts_by_accession(self, accession_number: str) -> None:
        """Clear existing parsed facts for idempotent re-parsing."""
        sql = "DELETE FROM xbrl_parsed_facts WHERE accession_number = ?;"
        with get_db_connection() as conn:
            conn.execute(sql, (accession_number,))

    def get_facts_by_accession(self, accession_number: str, entity_wide_only: bool = False) -> List[ParsedXBRLFact]:
        """Fetch parsed facts for an accession number, optionally filtering entity-wide facts."""
        if entity_wide_only:
            sql = "SELECT * FROM xbrl_parsed_facts WHERE accession_number = ? AND is_segment = 0;"
        else:
            sql = "SELECT * FROM xbrl_parsed_facts WHERE accession_number = ?;"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number,))
            rows = cursor.fetchall()
            return [
                ParsedXBRLFact(
                    id=r["id"],
                    accession_number=r["accession_number"],
                    concept_name=r["concept_name"],
                    namespace=r["namespace"],
                    is_custom=bool(r["is_custom"]),
                    value=r["value"],
                    numeric_value=r["numeric_value"],
                    unit=r["unit"],
                    context_id=r["context_id"],
                    period_type=r["period_type"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    is_segment=bool(r["is_segment"]),
                    dimensions=json.loads(r["dimensions_json"] or "{}"),
                    source_locator=r["source_locator"],
                    source_doc_hash=r["source_doc_hash"],
                    source_url=r["source_url"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

