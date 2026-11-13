import logging
from typing import Any, Dict, Optional
from app.sec.client import SECClient, normalize_cik, SECClientError

logger = logging.getLogger("filingguard.sec.company_facts")


class MalformedCompanyFactsError(SECClientError):
    """Raised when the Company Facts JSON structure is invalid or corrupt."""
    pass


class CompanyFactsClient:
    """Retrieves and validates official SEC Company Facts JSON."""

    def __init__(self, client: Optional[SECClient] = None):
        self.client = client or SECClient()

    def get_company_facts_url(self, cik: str) -> str:
        norm_cik = normalize_cik(cik)
        return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{norm_cik}.json"

    def fetch_company_facts(self, cik: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Retrieves company facts for a CIK, validates its structure,
        and returns the dictionary payload.
        """
        norm_cik = normalize_cik(cik)
        url = self.get_company_facts_url(norm_cik)
        data = self.client.get_json(url, use_cache=use_cache)

        if not isinstance(data, dict):
            raise MalformedCompanyFactsError(f"Company facts for CIK {norm_cik} is not a valid JSON object")

        if "facts" not in data or not isinstance(data["facts"], dict):
            raise MalformedCompanyFactsError(f"Company facts for CIK {norm_cik} missing required 'facts' structure")

        return data

