import logging
import re
from typing import Any, Dict, List, Optional
from app.sec.client import SECClient, normalize_accession_number, normalize_cik

logger = logging.getLogger("filingguard.sec.filing_index")


class FilingIndexResolver:
    """Retrieves filing directory indexes and resolves document URLs."""

    def __init__(self, client: Optional[SECClient] = None):
        self.client = client or SECClient()

    def get_archive_base_url(self, cik: str, accession_number: str) -> str:
        """
        Derives the SEC EDGAR archive directory base URL.
        CIK without leading zeroes and accession number without dashes.
        Example: https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/
        """
        norm_cik = normalize_cik(cik)
        accession_number = normalize_accession_number(accession_number)
        cik_no_zeros = str(int(norm_cik))
        accession_no_dashes = accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/"

    def get_filing_index(self, cik: str, accession_number: str) -> Dict[str, Any]:
        """Fetches the official index.json for a specific filing."""
        base_url = self.get_archive_base_url(cik, accession_number)
        index_url = f"{base_url}index.json"
        return self.client.get_json(index_url)

    def resolve_primary_document_url(
        self,
        cik: Any = None,
        accession_number: Optional[str] = None,
        primary_document: Optional[str] = None,
        filing: Any = None,
    ) -> Any:
        """
        Validates that primary document belongs to the accession archive,
        and constructs its full URL.
        Supports either:
          - (filing): a FilingRecord or FilingCandidate object; sets its primary_doc_url and returns the object.
          - (cik, accession_number, primary_document): returns the resolved URL string.
        """
        target = filing if filing is not None else cik
        if hasattr(target, "accession_number"):
            f = target
            c_cik = getattr(f, "cik", None)
            c_acc = getattr(f, "accession_number", None)
            c_pdoc = getattr(f, "primary_document", None)
            if c_cik and c_acc and c_pdoc:
                url = self._build_document_url(c_cik, c_acc, c_pdoc)
                f.primary_doc_url = url
            return f

        if not accession_number or not primary_document:
            raise ValueError("Both accession_number and primary_document are required when CIK is passed as a string.")

        return self._build_document_url(cik, accession_number, primary_document)

    def _build_document_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Helper to construct and validate archive document URL."""
        if not primary_document or not re.fullmatch(r"[A-Za-z0-9._-]+", primary_document):
            raise ValueError(f"Invalid SEC primary document name: {primary_document!r}")
        base_url = self.get_archive_base_url(cik, accession_number)
        full_url = f"{base_url}{primary_document}"
        return full_url

    def list_filing_documents(self, cik: str, accession_number: str) -> List[Dict[str, Any]]:
        """List all documents inside the filing index directory."""
        index_data = self.get_filing_index(cik, accession_number)
        directory_items = index_data.get("directory", {}).get("item", [])
        return directory_items
