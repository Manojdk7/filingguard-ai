import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.sec.client import (
    SECClient,
    normalize_cik,
    InvalidCIKError,
    SECClientError,
)
from app.sec.filing_index import FilingIndexResolver
from app.database.repositories.filing_repository import FilingRecord, FilingRepository

logger = logging.getLogger("filingguard.sec.submissions")


class NoEligibleFilingError(SECClientError):
    """Raised when no eligible filing of the requested form is found."""
    pass


class UnknownTickerError(SECClientError):
    """Raised when a ticker cannot be resolved from SEC's company directory."""
    pass


class FilingCandidate(BaseModel):
    accession_number: str
    form_type: str
    filing_date: str
    report_period: Optional[str] = None
    primary_document: Optional[str] = None
    primary_doc_url: Optional[str] = None
    is_amendment: bool = False
    amends_accession: Optional[str] = None


class SubmissionsManager:
    """Retrieves submissions and parses candidate 10-K and 10-K/A filings."""

    def __init__(
        self,
        client: Optional[SECClient] = None,
        index_resolver: Optional[FilingIndexResolver] = None,
        repository: Optional[FilingRepository] = None,
    ):
        self.client = client or SECClient()
        self.index_resolver = index_resolver or FilingIndexResolver(client=self.client)
        self.repository = repository or FilingRepository()

    def get_submissions_url(self, cik: str) -> str:
        norm_cik = normalize_cik(cik)
        return f"https://data.sec.gov/submissions/CIK{norm_cik}.json"

    def fetch_submissions(self, cik: str, use_cache: bool = True) -> Dict[str, Any]:
        """Fetch official submissions JSON for a given CIK."""
        url = self.get_submissions_url(cik)
        return self.client.get_json(url, use_cache=use_cache)

    def resolve_cik(self, cik_or_ticker: str) -> str:
        """Resolve a numeric CIK or ticker using the SEC's official company directory."""
        identifier = cik_or_ticker.strip().upper()
        if not identifier:
            raise InvalidCIKError("CIK or ticker cannot be empty")

        try:
            return normalize_cik(identifier)
        except InvalidCIKError:
            if identifier.isdigit():
                raise
            if not all(char.isalnum() or char in ".-" for char in identifier):
                raise InvalidCIKError(
                    "CIK or ticker may contain only letters, digits, periods, and hyphens"
                )

        directory = self.client.get_json("https://www.sec.gov/files/company_tickers.json")
        if not isinstance(directory, dict):
            raise SECClientError("SEC company ticker directory has an invalid response shape")

        matches = set()
        for record in directory.values():
            if (
                not isinstance(record, dict)
                or str(record.get("ticker", "")).strip().upper() != identifier
            ):
                continue
            try:
                matches.add(normalize_cik(record.get("cik_str")))
            except InvalidCIKError as exc:
                raise SECClientError(
                    f"SEC company directory has an invalid CIK for ticker '{identifier}'"
                ) from exc
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            raise UnknownTickerError(f"Ticker '{identifier}' maps to multiple SEC CIKs")
        raise UnknownTickerError(f"Ticker '{identifier}' was not found in the SEC company directory")

    def parse_recent_filings(self, cik: str, submissions_data: Dict[str, Any]) -> List[FilingCandidate]:
        """
        Parses recent filings list from submissions payload.
        Ensures 10-K and 10-K/A are properly identified.
        """
        recent = submissions_data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        accession_numbers = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_docs = recent.get("primaryDocument", [])

        candidates: List[FilingCandidate] = []
        count = len(accession_numbers)

        for i in range(count):
            form = forms[i] if i < len(forms) else ""
            acc = accession_numbers[i]
            f_date = filing_dates[i] if i < len(filing_dates) else ""
            r_date = report_dates[i] if i < len(report_dates) else None
            p_doc = primary_docs[i] if i < len(primary_docs) else None

            is_amendment = form == "10-K/A"

            if form in ("10-K", "10-K/A"):
                candidates.append(FilingCandidate(
                    accession_number=acc,
                    form_type=form,
                    filing_date=f_date,
                    report_period=r_date,
                    primary_document=p_doc,
                    is_amendment=is_amendment,
                    amends_accession=None,
                ))

        return candidates

    def select_latest_10k(
        self, submissions_data_or_cik: Any, include_amendments: bool = False
    ) -> Optional[FilingRecord]:
        """
        Selects the latest eligible 10-K from either submissions data dictionary
        or a CIK string, resolves primary document URL, and returns a FilingRecord.
        """
        if isinstance(submissions_data_or_cik, str):
            norm_cik = normalize_cik(submissions_data_or_cik)
            submissions_data = self.fetch_submissions(norm_cik)
        elif isinstance(submissions_data_or_cik, dict):
            submissions_data = submissions_data_or_cik
            raw_cik = submissions_data.get("cik")
            norm_cik = normalize_cik(str(raw_cik)) if raw_cik else "0000000000"
        else:
            raise ValueError(f"Expected dict or CIK str, got {type(submissions_data_or_cik)}")

        candidates = self.parse_recent_filings(norm_cik, submissions_data)
        eligible = [
            c for c in candidates
            if (c.form_type == "10-K" if not include_amendments else c.form_type in ("10-K", "10-K/A"))
        ]
        if not eligible:
            return None

        selected = eligible[0]
        if selected.primary_document:
            try:
                selected.primary_doc_url = self.index_resolver.resolve_primary_document_url(
                    norm_cik, selected.accession_number, selected.primary_document
                )
            except Exception as e:
                logger.warning(f"Could not resolve primary document URL for {selected.accession_number}: {e}")

        company_name = submissions_data.get("name")
        tickers = submissions_data.get("tickers", [])
        ticker = tickers[0] if tickers else None

        return FilingRecord(
            accession_number=selected.accession_number,
            cik=norm_cik,
            company_name=company_name,
            ticker=ticker,
            form_type=selected.form_type,
            filing_date=selected.filing_date,
            report_period=selected.report_period,
            primary_document=selected.primary_document,
            primary_doc_url=selected.primary_doc_url,
            is_amendment=selected.is_amendment,
            amends_accession=selected.amends_accession,
        )

    def get_latest_eligible_10k(self, cik: str, include_amendments: bool = False) -> FilingCandidate:
        """
        Selects the latest eligible 10-K filing.
        If include_amendments is False, amendments (10-K/A) are kept separate and not returned here.
        Raises NoEligibleFilingError if none found.
        """
        norm_cik = normalize_cik(cik)
        data = self.fetch_submissions(norm_cik)
        candidates = self.parse_recent_filings(norm_cik, data)

        eligible = [
            c for c in candidates
            if (c.form_type == "10-K" if not include_amendments else c.form_type in ("10-K", "10-K/A"))
        ]

        if not eligible:
            raise NoEligibleFilingError(f"No eligible 10-K filing found for CIK {norm_cik}")

        # Submissions recent filings are ordered descending by filingDate
        selected = eligible[0]

        # Resolve primary document URL
        if selected.primary_document:
            selected.primary_doc_url = self.index_resolver.resolve_primary_document_url(
                norm_cik, selected.accession_number, selected.primary_document
            )

        return selected

    def retrieve_and_persist_latest_10k(self, cik: str, company_name: Optional[str] = None, ticker: Optional[str] = None) -> FilingRecord:
        """
        Fetches submissions, selects latest 10-K, resolves document URL,
        and saves metadata idempotently to the SQLite repository.
        """
        norm_cik = normalize_cik(cik)
        data = self.fetch_submissions(norm_cik)
        resolved_company_name = company_name or data.get("name")
        tickers = data.get("tickers", [])
        resolved_ticker = ticker or (tickers[0] if tickers else None)

        selected = self.get_latest_eligible_10k(norm_cik, include_amendments=False)

        record = FilingRecord(
            accession_number=selected.accession_number,
            cik=norm_cik,
            company_name=resolved_company_name,
            ticker=resolved_ticker,
            form_type=selected.form_type,
            filing_date=selected.filing_date,
            report_period=selected.report_period,
            primary_document=selected.primary_document,
            primary_doc_url=selected.primary_doc_url,
            is_amendment=selected.is_amendment,
            amends_accession=selected.amends_accession,
        )

        self.repository.save(record)
        return record
