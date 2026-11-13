import pytest
from app.sec.submissions import SubmissionsManager
from app.database.repositories.filing_repository import FilingRepository


# Test companies: Apple (320193), Microsoft (789019), Amazon (1018724)
@pytest.mark.parametrize("cik,expected_ticker", [
    ("320193", "AAPL"),
    ("789019", "MSFT"),
    ("1018724", "AMZN"),
])
def test_live_sec_retrieval_and_persistence(cik, expected_ticker):
    manager = SubmissionsManager()
    repo = FilingRepository()

    record = manager.retrieve_and_persist_latest_10k(cik=cik)

    # Assertions on metadata
    assert record.accession_number is not None and len(record.accession_number) > 10
    assert record.form_type == "10-K"
    assert record.filing_date is not None
    assert record.primary_document is not None
    assert record.primary_doc_url is not None
    assert "Archives/edgar/data" in record.primary_doc_url
    assert record.ticker == expected_ticker

    # Check persistence in SQLite
    persisted = repo.get_by_accession(record.accession_number)
    assert persisted is not None
    assert persisted.cik == record.cik
    assert persisted.ticker == expected_ticker

