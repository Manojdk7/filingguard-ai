import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection
from app.sec.filing_download import DownloadedFiling

logger = logging.getLogger("filingguard.database.repositories.document")


class DocumentRepository:
    """Repository for managing downloaded filing documents and integrity hashes."""

    def save_downloaded_document(self, doc: DownloadedFiling) -> None:
        """Idempotently save or update downloaded document record."""
        sql = """
        INSERT INTO downloaded_documents (
            accession_number, cik, primary_document, source_url,
            local_path, file_size_bytes, sha256_hash, retrieved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(accession_number) DO UPDATE SET
            primary_document = excluded.primary_document,
            source_url = excluded.source_url,
            local_path = excluded.local_path,
            file_size_bytes = excluded.file_size_bytes,
            sha256_hash = excluded.sha256_hash,
            retrieved_at = excluded.retrieved_at;
        """
        with get_db_connection() as conn:
            conn.execute(sql, (
                doc.accession_number,
                doc.cik,
                doc.primary_document,
                doc.source_url,
                doc.local_path,
                doc.file_size_bytes,
                doc.sha256_hash,
                doc.retrieved_at,
            ))
        logger.debug(f"Saved document metadata for accession {doc.accession_number}")

    def get_by_accession(self, accession_number: str) -> Optional[DownloadedFiling]:
        """Fetch downloaded document metadata by accession number."""
        sql = "SELECT * FROM downloaded_documents WHERE accession_number = ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (accession_number,))
            row = cursor.fetchone()
            if row:
                return DownloadedFiling(
                    accession_number=row["accession_number"],
                    cik=row["cik"],
                    form_type="",
                    filing_date="",
                    primary_document=row["primary_document"],
                    source_url=row["source_url"],
                    local_path=row["local_path"],
                    file_size_bytes=row["file_size_bytes"],
                    sha256_hash=row["sha256_hash"],
                    retrieved_at=row["retrieved_at"],
                )
        return None

