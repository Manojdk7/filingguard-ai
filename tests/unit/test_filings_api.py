"""
Unit tests for SEC Filings API routes.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.repositories.filing_repository import FilingRecord

client = TestClient(app)


def test_list_filings_endpoint():
    """Verify GET /filings returns list of stored filings."""
    response = client.get("/filings")
    assert response.status_code == 200
    filings = response.json()
    assert isinstance(filings, list)
    assert len(filings) > 0
    first = filings[0]
    assert "accession_number" in first
    assert "cik" in first
    assert "form_type" in first


def test_get_filing_by_accession_success():
    """Verify GET /filings/{accession} returns metadata for existing filing."""
    # Use known Apple 10-K accession
    accn = "0000320193-26-000026"
    response = client.get(f"/filings/{accn}")
    assert response.status_code == 200
    data = response.json()
    assert data["accession_number"] == accn
    assert data["ticker"] == "AAPL"


def test_get_filing_by_accession_not_found():
    """Verify GET /filings/{accession} returns 404 for unknown accession."""
    response = client.get("/filings/9999999999-99-999999")
    assert response.status_code == 404


def test_ingest_filing_validation_error():
    """Verify POST /filings/ingest rejects empty request."""
    response = client.post("/filings/ingest", json={"cik_or_ticker": ""})
    assert response.status_code == 400


def test_ingest_filing_resolves_ticker_with_sec_directory(monkeypatch):
    import app.api.routes.filings as filings_route

    record = FilingRecord(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_name="Apple Inc.",
        ticker="AAPL",
        form_type="10-K",
        filing_date="2023-11-03",
        report_period="2023-09-30",
        primary_document="aapl-20230930.htm",
    )

    class FakeSubmissionsManager:
        def __init__(self, client):
            pass

        def resolve_cik(self, value):
            assert value == "AAPL"
            return "0000320193"

        def fetch_submissions(self, cik):
            assert cik == "0000320193"
            return {}

        def select_latest_10k(self, submissions):
            return record

    class FakeFilingIndexResolver:
        def __init__(self, client):
            pass

        def resolve_primary_document_url(self, filing):
            filing.primary_doc_url = (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019323000106/aapl-20230930.htm"
            )
            return filing

    monkeypatch.setattr(filings_route, "SECClient", lambda: object())
    monkeypatch.setattr(filings_route, "SubmissionsManager", FakeSubmissionsManager)
    monkeypatch.setattr(filings_route, "FilingIndexResolver", FakeFilingIndexResolver)
    monkeypatch.setattr(filings_route._filing_repo, "save", lambda filing: None)

    response = client.post(
        "/filings/ingest",
        json={"cik_or_ticker": "aapl", "form_type": "10-K"},
    )

    assert response.status_code == 201
    assert response.json()["cik"] == "0000320193"
    assert response.json()["ticker"] == "AAPL"
