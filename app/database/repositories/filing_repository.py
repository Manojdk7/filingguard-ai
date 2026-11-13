import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.filing")


class FilingRecord(BaseModel):
    accession_number: str
    cik: str
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    form_type: str
    filing_date: str
    report_period: Optional[str] = None
    primary_document: Optional[str] = None
    primary_doc_url: Optional[str] = None
    is_amendment: bool = False
    amends_accession: Optional[str] = None
    retrieved_at: Optional[str] = None


class FilingRepository:
    """Repository for persisting and querying filing metadata."""

    def save(self, filing: FilingRecord) -> None:
        """Idempotently save or update a filing record."""
        sql = """
        INSERT INTO filings (
            accession_number, cik, company_name, ticker, form_type,
            filing_date, report_period, primary_document, primary_doc_url,
            is_amendment, amends_accession, retrieved_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now', 'utc'))
        )
        ON CONFLICT(accession_number) DO UPDATE SET
            company_name = excluded.company_name,
            ticker = excluded.ticker,
            form_type = excluded.form_type,
            filing_date = excluded.filing_date,
            report_period = excluded.report_period,
            primary_document = excluded.primary_document,
            primary_doc_url = excluded.primary_doc_url,
            is_amendment = excluded.is_amendment,
            amends_accession = excluded.amends_accession,
            retrieved_at = datetime('now', 'utc');
        """
        with get_db_connection() as conn:
            conn.execute(sql, (
                filing.accession_number,
                filing.cik,
                filing.company_name,
                filing.ticker,
                filing.form_type,
                filing.filing_date,
                filing.report_period,
                filing.primary_document,
                filing.primary_doc_url,
                1 if filing.is_amendment else 0,
                filing.amends_accession,
                filing.retrieved_at,
            ))
        logger.debug(f"Saved filing metadata for accession: {filing.accession_number}")

    # Alias for method name compatibility
    save_filing = save

    def get_by_accession(self, accession_number: str) -> Optional[FilingRecord]:
        """Fetch a filing record by accession number."""
        sql = "SELECT * FROM filings WHERE accession_number = ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number,))
            row = cursor.fetchone()
            if row:
                return FilingRecord(
                    accession_number=row["accession_number"],
                    cik=row["cik"],
                    company_name=row["company_name"],
                    ticker=row["ticker"],
                    form_type=row["form_type"],
                    filing_date=row["filing_date"],
                    report_period=row["report_period"],
                    primary_document=row["primary_document"],
                    primary_doc_url=row["primary_doc_url"],
                    is_amendment=bool(row["is_amendment"]),
                    amends_accession=row["amends_accession"],
                    retrieved_at=row["retrieved_at"],
                )
        return None

    def list_by_cik(self, cik: str) -> List[FilingRecord]:
        """Fetch all filings for a given CIK."""
        sql = "SELECT * FROM filings WHERE cik = ? ORDER BY filing_date DESC;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (cik,))
            rows = cursor.fetchall()
            return [
                FilingRecord(
                    accession_number=r["accession_number"],
                    cik=r["cik"],
                    company_name=r["company_name"],
                    ticker=r["ticker"],
                    form_type=r["form_type"],
                    filing_date=r["filing_date"],
                    report_period=r["report_period"],
                    primary_document=r["primary_document"],
                    primary_doc_url=r["primary_doc_url"],
                    is_amendment=bool(r["is_amendment"]),
                    amends_accession=r["amends_accession"],
                    retrieved_at=r["retrieved_at"],
                )
                for r in rows
            ]

    def get_recent_filings(self, limit: int = 50) -> List[FilingRecord]:
        """Fetch recently retrieved or filed filings."""
        sql = "SELECT * FROM filings ORDER BY filing_date DESC, retrieved_at DESC LIMIT ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()
            return [
                FilingRecord(
                    accession_number=r["accession_number"],
                    cik=r["cik"],
                    company_name=r["company_name"],
                    ticker=r["ticker"],
                    form_type=r["form_type"],
                    filing_date=r["filing_date"],
                    report_period=r["report_period"],
                    primary_document=r["primary_document"],
                    primary_doc_url=r["primary_doc_url"],
                    is_amendment=bool(r["is_amendment"]),
                    amends_accession=r["amends_accession"],
                    retrieved_at=r["retrieved_at"],
                )
                for r in rows
            ]

