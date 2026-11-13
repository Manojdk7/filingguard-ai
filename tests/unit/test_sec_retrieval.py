import pytest
import time
from unittest.mock import MagicMock, patch
from app.sec.client import (
    normalize_cik,
    normalize_accession_number,
    InvalidCIKError,
    SECClient,
    SECClientError,
    SECRequestError,
)
from app.sec.cache import SECCache
from app.sec.filing_index import FilingIndexResolver
from app.sec.submissions import (
    SubmissionsManager,
    NoEligibleFilingError,
    UnknownTickerError,
    FilingCandidate,
)
from app.database.repositories.filing_repository import FilingRecord, FilingRepository


def test_cik_normalization_valid():
    assert normalize_cik("320193") == "0000320193"
    assert normalize_cik(789019) == "0000789019"
    assert normalize_cik("1018724") == "0001018724"
    assert normalize_cik("0000320193") == "0000320193"


def test_cik_normalization_invalid():
    with pytest.raises(InvalidCIKError):
        normalize_cik("")

    with pytest.raises(InvalidCIKError):
        normalize_cik(None)

    with pytest.raises(InvalidCIKError):
        normalize_cik("AAPL")

    with pytest.raises(InvalidCIKError):
        normalize_cik("1234567890123")  # Exceeds 10 digits


def test_accession_number_validation():
    accession = "0000320193-23-000106"
    assert normalize_accession_number(accession) == accession
    assert normalize_accession_number("0001193125-26-323660") == "0001193125-26-323660"
    with pytest.raises(ValueError, match="Invalid SEC accession"):
        normalize_accession_number("../invalid")


def test_ticker_resolution_uses_sec_company_directory():
    client = MagicMock(spec=SECClient)
    client.get_json.return_value = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
    }
    manager = SubmissionsManager(client=client)

    assert manager.resolve_cik("aapl") == "0000320193"
    client.get_json.assert_called_once_with("https://www.sec.gov/files/company_tickers.json")


def test_ticker_resolution_rejects_unknown_and_invalid_identifiers():
    client = MagicMock(spec=SECClient)
    client.get_json.return_value = {"0": {"cik_str": 320193, "ticker": "AAPL"}}
    manager = SubmissionsManager(client=client)

    with pytest.raises(UnknownTickerError):
        manager.resolve_cik("NOTFOUND")

    with pytest.raises(InvalidCIKError):
        manager.resolve_cik("AAPL/../MSFT")

    with pytest.raises(InvalidCIKError):
        manager.resolve_cik("12345678901")

    client.get_json.return_value = {"0": {"cik_str": "not-a-cik", "ticker": "AAPL"}}
    with pytest.raises(SECClientError, match="invalid CIK"):
        manager.resolve_cik("AAPL")


def test_sec_client_reports_malformed_json():
    cache = MagicMock()
    cache.get.return_value = None
    client = SECClient(cache=cache, max_retries=0)
    client.rate_limiter.wait = MagicMock()
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("invalid JSON")

    with patch("httpx.Client.get", return_value=response):
        with pytest.raises(SECRequestError, match="malformed JSON"):
            client.get_json("https://data.sec.gov/test.json")


def test_sec_client_rejects_unexpected_json_shape():
    cache = MagicMock()
    cache.get.return_value = None
    client = SECClient(cache=cache, max_retries=0)
    client.rate_limiter.wait = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = ["not", "an", "object"]

    with patch("httpx.Client.get", return_value=response):
        with pytest.raises(SECRequestError, match="unexpected JSON shape"):
            client.get_json("https://data.sec.gov/test.json")


def test_sec_client_retries_transient_document_download(monkeypatch):
    client = SECClient(cache=MagicMock(), max_retries=1, backoff_factor=0)
    client.rate_limiter.wait = MagicMock()
    temporary = MagicMock(status_code=503)
    successful = MagicMock(status_code=200, content=b"official filing")
    mock_get = MagicMock(side_effect=[temporary, successful])
    monkeypatch.setattr("httpx.Client.get", mock_get)
    monkeypatch.setattr("app.sec.client.time.sleep", lambda _: None)

    assert client.get_bytes("https://www.sec.gov/Archives/test.htm") == b"official filing"
    assert mock_get.call_count == 2


def test_cache_hit_and_expiry(tmp_path):
    cache = SECCache(cache_dir=tmp_path, ttl_hours=1, enabled=True)
    key = "https://example.com/test.json"
    data = {"company": "TestCorp", "value": 100}

    # Initial miss
    assert cache.get(key) is None

    # Set and get (hit)
    cache.set(key, data)
    assert cache.get(key) == data

    # Test expiry by reducing ttl
    cache.ttl_seconds = -1
    assert cache.get(key) is None


def test_cache_corrupted_file_handling(tmp_path):
    cache = SECCache(cache_dir=tmp_path, ttl_hours=1, enabled=True)
    key = "https://example.com/corrupt.json"
    cache_file = cache._get_cache_path(key)

    # Write corrupt JSON
    cache_file.write_text("{invalid_json: true", encoding="utf-8")
    assert cache.get(key) is None
    # File should be removed after encountering corruption
    assert not cache_file.exists()


def test_filing_index_url_resolution():
    resolver = FilingIndexResolver()
    base_url = resolver.get_archive_base_url("0000320193", "0000320193-23-000106")
    assert base_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"

    doc_url = resolver.resolve_primary_document_url("0000320193", "0000320193-23-000106", "aapl-20230930.htm")
    assert doc_url == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"


def test_filing_index_accepts_accession_number_with_different_cik_prefix():
    resolver = FilingIndexResolver()
    base_url = resolver.get_archive_base_url(
        "0000789019", "0001193125-26-323660"
    )

    assert base_url == (
        "https://www.sec.gov/Archives/edgar/data/789019/"
        "000119312526323660/"
    )


def test_submissions_parsing_and_10k_selection():
    mock_submissions = {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-24-000001",
                    "0000320193-23-000999",
                    "0000320193-23-000106",
                ],
                "form": ["10-Q", "10-K/A", "10-K"],
                "filingDate": ["2024-02-01", "2023-11-15", "2023-11-03"],
                "reportDate": ["2023-12-30", "2023-09-30", "2023-09-30"],
                "primaryDocument": ["aapl-20231230.htm", "aapl-20230930a.htm", "aapl-20230930.htm"],
            }
        }
    }

    client = MagicMock(spec=SECClient)
    client.get_json.return_value = mock_submissions

    manager = SubmissionsManager(client=client)

    # Standard call selects latest 10-K and ignores 10-Q and 10-K/A
    selected = manager.get_latest_eligible_10k("320193", include_amendments=False)
    assert selected.accession_number == "0000320193-23-000106"
    assert selected.form_type == "10-K"
    assert selected.is_amendment is False

    # 10-K/A should be tracked distinctly
    candidates = manager.parse_recent_filings("320193", mock_submissions)
    amendment = next(c for c in candidates if c.form_type == "10-K/A")
    assert amendment.accession_number == "0000320193-23-000999"
    assert amendment.is_amendment is True


def test_no_eligible_10k_error():
    mock_submissions = {
        "cik": "0000999999",
        "filings": {
            "recent": {
                "accessionNumber": ["0000999999-24-000001"],
                "form": ["8-K"],
                "filingDate": ["2024-01-01"],
                "reportDate": ["2024-01-01"],
                "primaryDocument": ["doc.htm"],
            }
        }
    }

    client = MagicMock(spec=SECClient)
    client.get_json.return_value = mock_submissions
    manager = SubmissionsManager(client=client)

    with pytest.raises(NoEligibleFilingError):
        manager.get_latest_eligible_10k("999999")


def test_filing_metadata_persistence_and_idempotency(tmp_path):
    repo = FilingRepository()
    record = FilingRecord(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_name="Apple Inc.",
        ticker="AAPL",
        form_type="10-K",
        filing_date="2023-11-03",
        report_period="2023-09-30",
        primary_document="aapl-20230930.htm",
        primary_doc_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        is_amendment=False,
    )

    # Initial save
    repo.save(record)
    fetched = repo.get_by_accession("0000320193-23-000106")
    assert fetched is not None
    assert fetched.company_name == "Apple Inc."
    assert fetched.ticker == "AAPL"

    # Idempotent re-save with updated field
    record.company_name = "Apple Inc. Updated"
    repo.save(record)
    updated = repo.get_by_accession("0000320193-23-000106")
    assert updated is not None
    assert updated.company_name == "Apple Inc. Updated"


def test_sec_client_retry_and_outage_handling():
    client = SECClient(max_retries=2, backoff_factor=0.01)

    with patch("httpx.Client.get") as mock_get:
        # Simulate consecutive 503 Server Errors
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response

        with pytest.raises(SECRequestError) as exc_info:
            client.get_json("https://data.sec.gov/submissions/CIK0000320193.json", use_cache=False)

        assert "Failed to fetch SEC resource" in str(exc_info.value)
        # 1 initial + 2 retries = 3 calls
        assert mock_get.call_count == 3


def test_submissions_manager_select_latest_10k():
    mock_submissions = {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000026", "0000320193-25-000001"],
                "form": ["10-K", "10-Q"],
                "filingDate": ["2026-10-30", "2025-07-25"],
                "reportDate": ["2026-09-26", "2025-06-28"],
                "primaryDocument": ["aapl-20260926.htm", "aapl-20250628.htm"],
            }
        },
    }

    client = MagicMock(spec=SECClient)
    client.get_json.return_value = mock_submissions
    resolver = FilingIndexResolver(client=client)
    manager = SubmissionsManager(client=client, index_resolver=resolver)

    # Call select_latest_10k with submissions dictionary
    filing = manager.select_latest_10k(mock_submissions)
    assert filing is not None
    assert filing.accession_number == "0000320193-26-000026"
    assert filing.company_name == "Apple Inc."
    assert filing.ticker == "AAPL"
    assert filing.form_type == "10-K"
    assert "aapl-20260926.htm" in filing.primary_doc_url

    # Test resolver flexibility accepting filing object
    mutated = resolver.resolve_primary_document_url(filing)
    assert mutated.accession_number == filing.accession_number
    assert "https://www.sec.gov" in mutated.primary_doc_url
