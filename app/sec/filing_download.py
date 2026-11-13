import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit
from pydantic import BaseModel
from app.config import settings
from app.sec.client import SECClient, SECRequestError, normalize_accession_number, normalize_cik

logger = logging.getLogger("filingguard.sec.filing_download")


class DownloadedFiling(BaseModel):
    accession_number: str
    cik: str
    form_type: str
    filing_date: str
    primary_document: str
    source_url: str
    local_path: str
    file_size_bytes: int
    sha256_hash: str
    retrieved_at: str


class FilingDownloader:
    """
    Downloads original primary filing documents (HTML / Inline XBRL),
    verifies document types, computes SHA-256 integrity hashes,
    and caches documents locally in `data/filings/`.
    """

    def __init__(
        self,
        client: Optional[SECClient] = None,
        filings_dir: Optional[Path] = None,
    ):
        self.client = client or SECClient()
        self.filings_dir = filings_dir or (settings.DATA_DIR / "filings")
        self.filings_dir.mkdir(parents=True, exist_ok=True)

    def calculate_sha256(self, file_path: Path) -> str:
        """Computes the SHA-256 hash of a file."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def get_filing_storage_path(self, accession_number: str, primary_document: str) -> Path:
        """Generates destination path: data/filings/{accession_number}/{primary_document}."""
        accession_number = normalize_accession_number(accession_number)
        if not primary_document or not re.fullmatch(r"[A-Za-z0-9._-]+", primary_document):
            raise ValueError(f"Invalid SEC primary document name: {primary_document!r}")
        target_dir = self.filings_dir / accession_number
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / primary_document

    def download_filing(
        self,
        cik: Any = None,
        accession_number: Optional[str] = None,
        form_type: Optional[str] = None,
        filing_date: Optional[str] = None,
        primary_document: Optional[str] = None,
        source_url: Optional[str] = None,
        force_redownload: bool = False,
        filing: Any = None,
    ) -> DownloadedFiling:
        """
        Downloads original filing from SEC EDGAR archive, verifies response,
        computes SHA-256 hash, and returns DownloadedFiling metadata.
        Avoids redundant downloading if file already exists locally.
        Supports either:
          - (filing): a FilingRecord or FilingCandidate object.
          - (cik, accession_number, form_type, filing_date, primary_document, source_url).
        """
        target = filing if filing is not None else cik
        if hasattr(target, "accession_number"):
            f = target
            c_cik = getattr(f, "cik", "")
            c_acc = getattr(f, "accession_number", "")
            c_form = getattr(f, "form_type", "10-K")
            c_date = getattr(f, "filing_date", "")
            c_pdoc = getattr(f, "primary_document", "")
            c_url = getattr(f, "primary_doc_url", None) or source_url or ""
            return self._download_filing_internal(
                cik=c_cik,
                accession_number=c_acc,
                form_type=c_form,
                filing_date=c_date,
                primary_document=c_pdoc,
                source_url=c_url,
                force_redownload=force_redownload,
            )

        return self._download_filing_internal(
            cik=cik,
            accession_number=accession_number,
            form_type=form_type or "10-K",
            filing_date=filing_date or "",
            primary_document=primary_document or "",
            source_url=source_url or "",
            force_redownload=force_redownload,
        )

    def _download_filing_internal(
        self,
        cik: str,
        accession_number: str,
        form_type: str,
        filing_date: str,
        primary_document: str,
        source_url: str,
        force_redownload: bool = False,
    ) -> DownloadedFiling:
        cik = normalize_cik(cik)
        accession_number = normalize_accession_number(accession_number)
        if not primary_document or not re.fullmatch(r"[A-Za-z0-9._-]+", primary_document):
            raise ValueError(f"Invalid SEC primary document name: {primary_document!r}")
        parsed_url = urlsplit(source_url)
        expected_archive = (
            f"/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/"
        )
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "www.sec.gov"
            or not parsed_url.path.startswith(expected_archive)
            or parsed_url.path != f"{expected_archive}{primary_document}"
        ):
            raise ValueError(
                f"Filing URL must reference the expected SEC archive document: {source_url!r}"
            )

        local_path = self.get_filing_storage_path(accession_number, primary_document)

        if not force_redownload and local_path.exists() and local_path.stat().st_size > 0:
            logger.info(f"Filing document already cached locally at {local_path}")
            sha256 = self.calculate_sha256(local_path)
            file_size = local_path.stat().st_size
            import datetime
            mtime = datetime.datetime.fromtimestamp(local_path.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
            return DownloadedFiling(
                accession_number=accession_number,
                cik=cik,
                form_type=form_type,
                filing_date=filing_date,
                primary_document=primary_document,
                source_url=source_url,
                local_path=str(local_path),
                file_size_bytes=file_size,
                sha256_hash=sha256,
                retrieved_at=mtime,
            )

        logger.info(f"Downloading original filing document from {source_url} to {local_path}")

        try:
            content = self.client.get_bytes(source_url)
            if not content:
                raise SECRequestError(f"Downloaded empty filing document from {source_url}")

            with open(local_path, "wb") as f:
                f.write(content)

            sha256 = self.calculate_sha256(local_path)
            file_size = len(content)

            import datetime
            retrieved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

            return DownloadedFiling(
                accession_number=accession_number,
                cik=cik,
                form_type=form_type,
                filing_date=filing_date,
                primary_document=primary_document,
                source_url=source_url,
                local_path=str(local_path),
                file_size_bytes=file_size,
                sha256_hash=sha256,
                retrieved_at=retrieved_at,
            )

        except Exception as e:
            if local_path.exists():
                try:
                    local_path.unlink()
                except OSError:
                    pass
            logger.error(f"Error downloading filing document {source_url}: {e}")
            raise
