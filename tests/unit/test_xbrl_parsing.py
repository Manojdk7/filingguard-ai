import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.sec.filing_download import FilingDownloader, DownloadedFiling
from app.extraction.arelle_runner import ArelleRunner, ArelleRunResult
from app.extraction.xbrl_parser import InlineXBRLParser, ParsedXBRLFact
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.xbrl_fact_repository import XBRLFactRepository
from app.sec.client import SECRequestError


def test_sha256_hash_consistency(tmp_path):
    downloader = FilingDownloader(filings_dir=tmp_path)
    test_file = tmp_path / "sample.htm"
    content = b"<html><body>Test SEC Filing Content</body></html>"
    test_file.write_bytes(content)

    hash1 = downloader.calculate_sha256(test_file)
    hash2 = downloader.calculate_sha256(test_file)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 is 64 hex chars


def test_invalid_filing_url_rejection(tmp_path):
    downloader = FilingDownloader(filings_dir=tmp_path)
    with pytest.raises(ValueError) as exc:
        downloader.download_filing(
            cik="0000320193",
            accession_number="0000320193-23-000106",
            form_type="10-K",
            filing_date="2023-11-03",
            primary_document="aapl-20230930.htm",
            source_url="ftp://invalid-url.com/doc.htm",
        )
    assert "expected SEC archive document" in str(exc.value)


def test_failed_sec_download_handling(tmp_path):
    downloader = FilingDownloader(filings_dir=tmp_path)
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(SECRequestError) as exc:
            downloader.download_filing(
                cik="0000320193",
                accession_number="0000320193-23-000106",
                form_type="10-K",
                filing_date="2023-11-03",
                primary_document="missing.htm",
                source_url=(
                    "https://www.sec.gov/Archives/edgar/data/320193/"
                    "000032019323000106/missing.htm"
                ),
            )
        assert "SEC returned HTTP 404" in str(exc.value)


def test_filing_download_accepts_accession_prefix_different_from_issuer_cik(tmp_path):
    downloader = FilingDownloader(filings_dir=tmp_path)
    with pytest.raises(ValueError, match="primary document"):
        downloader.get_filing_storage_path(
            "0000320193-23-000106", "..\\outside.htm"
        )

    downloader.client.get_bytes = MagicMock(return_value=b"official filing")
    downloaded = downloader.download_filing(
        cik="0000789019",
        accession_number="0001193125-26-323660",
        primary_document="msft.htm",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312526323660/msft.htm"
        ),
    )
    assert downloaded.accession_number == "0001193125-26-323660"
    assert downloaded.cik == "0000789019"


def test_filing_download_rejects_archive_path_with_wrong_issuer_cik(tmp_path):
    downloader = FilingDownloader(filings_dir=tmp_path)
    with pytest.raises(ValueError, match="expected SEC archive document"):
        downloader.download_filing(
            cik="0000789019",
            accession_number="0001193125-26-323660",
            primary_document="msft.htm",
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000119312526323660/msft.htm"
            ),
        )


def test_arelle_runner_file_not_found():
    runner = ArelleRunner()
    result, model = runner.parse_filing("non_existent_file.htm")
    assert result.success is False
    assert "File not found" in result.error_message
    assert model is None


def test_arelle_runner_processing_error():
    runner = ArelleRunner()
    with patch("arelle.Cntlr.Cntlr") as mock_cntlr_cls:
        mock_cntlr_cls.side_effect = Exception("Arelle syntax parse failure")
        result, model = runner.parse_filing(__file__)
        assert result.success is False
        assert "Arelle syntax parse failure" in result.error_message
        assert model is None


def test_xbrl_parser_fact_and_dimension_extraction():
    # Mock Arelle ModelXbrl object and internal structures
    mock_runner = MagicMock(spec=ArelleRunner)
    parser = InlineXBRLParser(arelle_runner=mock_runner)

    # 1. Instant Entity-Wide Fact (Total Assets)
    fact1 = MagicMock()
    fact1.qname.localName = "Assets"
    fact1.qname.namespaceURI = "http://fasb.org/us-gaap/2023"
    fact1.qname.prefix = "us-gaap"
    fact1.value = "352583000000"
    fact1.xValue = 352583000000.0
    fact1.isNumeric = True
    fact1.context.id = "c_instant_2023"
    fact1.context.isInstantPeriod = True
    fact1.context.isStartEndPeriod = False
    fact1.context.instantDatetime.date.return_value = "2023-09-30"
    fact1.context.hasSegment = False
    fact1.unit.measures = [[MagicMock(localName="USD")]]
    fact1.sourceline = 1250

    # 2. Duration Segment Fact (Revenue for iPhone segment)
    fact2 = MagicMock()
    fact2.qname.localName = "RevenueFromContractWithCustomerExcludingAssessedTax"
    fact2.qname.namespaceURI = "http://fasb.org/us-gaap/2023"
    fact2.qname.prefix = "us-gaap"
    fact2.value = "200583000000"
    fact2.xValue = 200583000000.0
    fact2.isNumeric = True
    fact2.context.id = "c_duration_iphone"
    fact2.context.isInstantPeriod = False
    fact2.context.isStartEndPeriod = True
    fact2.context.startDatetime.date.return_value = "2022-10-01"
    fact2.context.endDatetime.date.return_value = "2023-09-30"
    fact2.context.hasSegment = True
    # Dimensional segment mock
    dim_qname = MagicMock(localName="ProductOrServiceAxis")
    dim_val = MagicMock()
    dim_val.memberQname.localName = "IPhoneMember"
    fact2.context.qnameDims = {dim_qname: dim_val}
    fact2.unit.measures = [[MagicMock(localName="USD")]]
    fact2.sourceline = 2100

    # 3. Custom Company-specific Fact (e.g. aapl:CommercialPaperWeightedAverageInterestRate)
    fact3 = MagicMock()
    fact3.qname.localName = "CommercialPaperWeightedAverageInterestRate"
    fact3.qname.namespaceURI = "http://apple.com/20230930"
    fact3.qname.prefix = "aapl"
    fact3.value = "0.054"
    fact3.xValue = 0.054
    fact3.isNumeric = True
    fact3.context.id = "c_custom_instant"
    fact3.context.isInstantPeriod = True
    fact3.context.isStartEndPeriod = False
    fact3.context.instantDatetime.date.return_value = "2023-09-30"
    fact3.context.hasSegment = False
    fact3.unit.measures = [[MagicMock(localName="pure")]]
    fact3.sourceline = 4500

    mock_model = MagicMock()
    mock_model.facts = [fact1, fact2, fact3]
    mock_model.contexts = [fact1.context, fact2.context, fact3.context]
    mock_model.units = [fact1.unit, fact3.unit]

    run_res = ArelleRunResult(
        success=True,
        file_path="mock_filing.htm",
        facts_count=3,
        contexts_count=3,
        units_count=2,
    )
    mock_runner.parse_filing.return_value = (run_res, mock_model)

    parsed_facts, summary = parser.parse_document(
        local_file_path="mock_filing.htm",
        accession_number="0000320193-23-000106",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        source_doc_hash="mock_hash_123",
    )

    assert len(parsed_facts) == 3
    assert summary.total_facts == 3
    assert summary.entity_wide_facts == 2
    assert summary.dimensional_facts == 1
    assert summary.custom_facts == 1
    assert summary.standard_facts == 2

    # Verify entity-wide fact
    f_assets = next(f for f in parsed_facts if f.concept_name == "Assets")
    assert f_assets.is_segment is False
    assert f_assets.is_custom is False
    assert f_assets.period_type == "instant"
    assert f_assets.numeric_value == 352583000000.0
    assert f_assets.source_locator == "line_1250"

    # Verify segment fact
    f_iphone = next(f for f in parsed_facts if f.concept_name == "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert f_iphone.is_segment is True
    assert f_iphone.dimensions == {"ProductOrServiceAxis": "IPhoneMember"}
    assert f_iphone.period_type == "duration"

    # Verify custom fact
    f_custom = next(f for f in parsed_facts if f.concept_name == "CommercialPaperWeightedAverageInterestRate")
    assert f_custom.is_custom is True
    assert f_custom.namespace == "http://apple.com/20230930"
    assert f_custom.unit == "pure"


def test_document_and_xbrl_persistence():
    doc_repo = DocumentRepository()
    xbrl_repo = XBRLFactRepository()

    doc = DownloadedFiling(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        form_type="10-K",
        filing_date="2023-11-03",
        primary_document="aapl-20230930.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        local_path="data/filings/0000320193-23-000106/aapl-20230930.htm",
        file_size_bytes=1048576,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        retrieved_at="2026-11-12T10:00:00Z",
    )
    doc_repo.save_downloaded_document(doc)

    fetched_doc = doc_repo.get_by_accession("0000320193-23-000106")
    assert fetched_doc is not None
    assert fetched_doc.sha256_hash == doc.sha256_hash
    assert fetched_doc.file_size_bytes == 1048576

    fact = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="Assets",
        namespace="http://fasb.org/us-gaap/2023",
        is_custom=False,
        value="352583000000",
        numeric_value=352583000000.0,
        unit="USD",
        context_id="c_instant",
        period_type="instant",
        start_date=None,
        end_date="2023-09-30",
        is_segment=False,
        dimensions={},
        source_locator="line_100",
        source_doc_hash=doc.sha256_hash,
        source_url=doc.source_url,
    )

    xbrl_repo.delete_facts_by_accession("0000320193-23-000106")
    xbrl_repo.save_facts([fact])

    persisted_facts = xbrl_repo.get_facts_by_accession("0000320193-23-000106", entity_wide_only=True)
    assert len(persisted_facts) == 1
    assert persisted_facts[0].concept_name == "Assets"
    assert persisted_facts[0].is_segment is False
    assert persisted_facts[0].source_doc_hash == doc.sha256_hash




def test_negative_accounting_parsing():
    """EXT-02: Verify that standard financial accounting representations of negative numbers,
    zeros, currency symbols, commas, decimals, malformed strings, and XBRL sign/scale attributes
    are correctly and robustly parsed without double-negation."""
    from app.extraction.xbrl_parser import parse_accounting_number

    # 1. Required test cases from spec
    spec_test_cases = {
        "(1,234.56)": -1234.56,
        "1,234.56-": -1234.56,
        "-1,234.56": -1234.56,
        "1,234.56": 1234.56,
        "0": 0.0,
        "(500)": -500.0,
        "500-": -500.0,
    }
    for raw_input, expected in spec_test_cases.items():
        parsed = parse_accounting_number(raw_input)
        assert parsed == pytest.approx(expected), f"Failed for input '{raw_input}': got {parsed}, expected {expected}"

    # 2. Large numbers with commas and currency symbols
    assert parse_accounting_number("(1,500,000)") == -1500000.0
    assert parse_accounting_number("1,500,000-") == -1500000.0
    assert parse_accounting_number("-1,500,000") == -1500000.0
    assert parse_accounting_number("$(1,500,000)") == -1500000.0
    assert parse_accounting_number("($1,500,000)") == -1500000.0
    assert parse_accounting_number("-$1,500,000") == -1500000.0
    assert parse_accounting_number("€(2,750.50)") == -2750.50
    assert parse_accounting_number("£1,234.56-") == -1234.56
    assert parse_accounting_number("¥(500,000)") == -500000.0

    # 3. Zero, negative zero, and decimal representations
    assert parse_accounting_number("0.0") == 0.0
    assert parse_accounting_number("(0)") == 0.0
    assert parse_accounting_number("-0") == 0.0
    assert parse_accounting_number("0.00-") == 0.0
    assert parse_accounting_number("+1,234.56") == 1234.56
    assert parse_accounting_number("  (  1,234.56  )  ") == -1234.56

    # 4. Numeric input pass-through
    assert parse_accounting_number(1234.56) == 1234.56
    assert parse_accounting_number(-1234.56) == -1234.56
    assert parse_accounting_number(0) == 0.0

    # 5. Malformed, empty, and non-numeric inputs return None (not 0.0)
    assert parse_accounting_number("") is None
    assert parse_accounting_number("   ") is None
    assert parse_accounting_number("N/A") is None
    assert parse_accounting_number("--") is None
    assert parse_accounting_number("abc") is None
    assert parse_accounting_number(None) is None
    assert parse_accounting_number([]) is None
    assert parse_accounting_number({}) is None
    assert parse_accounting_number(float("nan")) is None
    assert parse_accounting_number(float("inf")) is None

    # 6. XBRL sign attribute handling without double-negation
    # When value is positive and sign='-', result is negative
    assert parse_accounting_number("1,234.56", sign="-") == -1234.56
    # When value is ALREADY negative (e.g. parentheses) and sign='-', NO double negation!
    assert parse_accounting_number("(1,234.56)", sign="-") == -1234.56
    assert parse_accounting_number("-1,234.56", sign="-") == -1234.56
    assert parse_accounting_number("1,234.56-", sign="-") == -1234.56

    # 7. XBRL scale attribute handling
    assert parse_accounting_number("1.5", scale=6) == 1500000.0
    assert parse_accounting_number("(500)", scale=3) == -500000.0



def test_arelle_resource_cleanup():
    """SYS-01: Verify that Arelle runner and parser cleanly close ModelXbrl, FileSource, and Cntlr
    upon successful parsing, upon parsing failures, upon mid-extraction exceptions, and during
    repeated executions without accumulating unclosed resources."""
    mock_runner = MagicMock(spec=ArelleRunner)
    parser = InlineXBRLParser(arelle_runner=mock_runner)

    # 1. Successful parsing closes resources
    mock_fact = MagicMock()
    mock_fact.qname.localName = "Assets"
    mock_fact.qname.namespaceURI = "http://fasb.org/us-gaap/2023"
    mock_fact.qname.prefix = "us-gaap"
    mock_fact.value = "1000000"
    mock_fact.context.id = "c1"
    mock_fact.context.isInstantPeriod = True
    mock_fact.context.instantDatetime.date.return_value = "2023-09-30"
    mock_fact.context.hasSegment = False
    mock_fact.unit.measures = [[MagicMock(localName="USD")]]

    mock_model = MagicMock()
    mock_model.facts = [mock_fact]
    mock_model.contexts = [mock_fact.context]
    mock_model.units = [mock_fact.unit]
    mock_model.close = MagicMock()

    mock_cntlr = MagicMock()
    mock_filesource = MagicMock()
    mock_model._cntlr = mock_cntlr
    mock_model._file_source = mock_filesource

    run_res = ArelleRunResult(
        success=True,
        file_path="mock_filing.htm",
        facts_count=1,
        contexts_count=1,
        units_count=1,
    )
    mock_runner.parse_filing.return_value = (run_res, mock_model)

    parsed_facts, summary = parser.parse_document(
        local_file_path="mock_filing.htm",
        accession_number="0000320193-23-000106",
        source_url="https://example.com/doc.htm",
        source_doc_hash="hash123",
    )

    # Verify that close_model was called
    mock_runner.close_model.assert_called_once_with(mock_model)
    # Extracted data is pure application-owned objects
    assert len(parsed_facts) == 1
    assert parsed_facts[0].concept_name == "Assets"
    assert parsed_facts[0].numeric_value == 1000000.0
    assert summary.total_facts == 1

    # 2. Real ArelleRunner.close_model closes model, file_source, and cntlr
    real_runner = ArelleRunner()
    real_runner.close_model(mock_model)
    mock_model.close.assert_called_once()
    mock_filesource.close.assert_called_once()
    mock_cntlr.close.assert_called_once()

    # 3. Mid-extraction exception still triggers cleanup in finally block
    failing_model = MagicMock()
    # Making model.facts iteration raise an unhandled exception
    def _raise_error():
        raise RuntimeError("Disk read corruption during iteration")
    type(failing_model).facts = property(lambda self: _raise_error())

    mock_runner.reset_mock()
    mock_runner.parse_filing.return_value = (run_res, failing_model)

    with pytest.raises(RuntimeError, match="Disk read corruption"):
        parser.parse_document(
            local_file_path="mock_filing.htm",
            accession_number="0000320193-23-000106",
            source_url="https://example.com/doc.htm",
            source_doc_hash="hash123",
        )

    # close_model must still be called in finally
    mock_runner.close_model.assert_called_once_with(failing_model)

    # 4. Parsing failure (e.g. runner returns success=False) handles cleanup safely
    mock_runner.reset_mock()
    fail_res = ArelleRunResult(
        success=False,
        file_path="missing.htm",
        error_message="Arelle syntax failure",
    )
    mock_runner.parse_filing.return_value = (fail_res, None)

    empty_facts, empty_sum = parser.parse_document(
        local_file_path="missing.htm",
        accession_number="0000320193-23-000106",
        source_url="https://example.com/missing.htm",
        source_doc_hash="hash123",
    )
    assert len(empty_facts) == 0
    assert empty_sum.total_facts == 0

    # 5. Repeated parsing calls execute cleanup on every cycle
    mock_runner.reset_mock()
    mock_runner.parse_filing.return_value = (run_res, mock_model)
    for _ in range(5):
        parser.parse_document("mock.htm", "accn", "url", "hash")
    assert mock_runner.close_model.call_count == 5
