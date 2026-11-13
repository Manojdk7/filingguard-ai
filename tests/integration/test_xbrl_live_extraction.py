import pytest
from app.sec.submissions import SubmissionsManager
from app.sec.filing_download import FilingDownloader
from app.extraction.xbrl_parser import InlineXBRLParser
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.xbrl_fact_repository import XBRLFactRepository


def test_live_original_filing_download_and_ixbrl_parsing_apple():
    sub_mgr = SubmissionsManager()
    filing = sub_mgr.retrieve_and_persist_latest_10k("320193")
    assert filing.primary_doc_url is not None

    downloader = FilingDownloader()
    downloaded = downloader.download_filing(
        cik=filing.cik,
        accession_number=filing.accession_number,
        form_type=filing.form_type,
        filing_date=filing.filing_date,
        primary_document=filing.primary_document,
        source_url=filing.primary_doc_url,
    )

    # Document integrity and download assertions
    assert downloaded.accession_number == filing.accession_number
    assert downloaded.file_size_bytes > 500000
    assert len(downloaded.sha256_hash) == 64

    # Document metadata persistence
    doc_repo = DocumentRepository()
    doc_repo.save_downloaded_document(downloaded)
    stored_doc = doc_repo.get_by_accession(downloaded.accession_number)
    assert stored_doc is not None
    assert stored_doc.sha256_hash == downloaded.sha256_hash

    # Parse Inline XBRL document with Arelle
    parser = InlineXBRLParser()
    facts, summary = parser.parse_document(
        local_file_path=downloaded.local_path,
        accession_number=downloaded.accession_number,
        source_url=downloaded.source_url,
        source_doc_hash=downloaded.sha256_hash,
    )

    assert summary.total_facts > 1000
    assert summary.entity_wide_facts > 500
    assert summary.dimensional_facts > 300
    assert summary.custom_facts > 50
    assert summary.contexts_count > 100
    assert summary.units_count > 0

    # Test separation of entity-wide vs segment facts
    dim_facts = [f for f in facts if f.is_segment]
    entity_facts = [f for f in facts if not f.is_segment]
    assert len(dim_facts) == summary.dimensional_facts
    assert len(entity_facts) == summary.entity_wide_facts

    # Custom concepts preserved (Apple custom extension namespace contains apple.com)
    custom_facts = [f for f in facts if f.is_custom]
    assert len(custom_facts) == summary.custom_facts
    assert any("apple.com" in f.namespace.lower() for f in custom_facts)

    # Persist parsed facts
    xbrl_repo = XBRLFactRepository()
    xbrl_repo.delete_facts_by_accession(downloaded.accession_number)
    xbrl_repo.save_facts(facts)

    db_entity_facts = xbrl_repo.get_facts_by_accession(downloaded.accession_number, entity_wide_only=True)
    assert len(db_entity_facts) == summary.entity_wide_facts
