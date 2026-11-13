import pytest
from app.extraction.metric_extractor import MetricExtractor
from app.extraction.xbrl_parser import InlineXBRLParser
from app.extraction.reconciliation_service import CrossSourceReconciliationService
from app.extraction.semantic_mapping import SemanticMapper
from app.extraction.segment_classifier import SegmentClassifier
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.xbrl_fact_repository import XBRLFactRepository
from app.database.repositories.reconciliation_repository import ReconciliationRepository


def test_live_reconciliation_apple():
    accn = "0000320193-26-000026"
    doc_repo = DocumentRepository()
    doc = doc_repo.get_by_accession(accn)
    assert doc is not None

    # Load previously parsed iXBRL facts
    xbrl_repo = XBRLFactRepository()
    ix_facts = xbrl_repo.get_facts_by_accession(accn)
    assert len(ix_facts) > 1000

    # Load Company Facts
    fact_repo = FactRepository()
    cf_facts = fact_repo.get_selected_facts_by_accession(accn)
    assert len(cf_facts) == 10

    # Perform cross-source reconciliation
    recon_service = CrossSourceReconciliationService()
    results = recon_service.reconcile_facts_for_filing(
        accession_number=accn,
        cik="0000320193",
        company_facts=cf_facts,
        ixbrl_facts=ix_facts,
    )

    assert len(results) == 10

    # Verify that all 10 canonical metrics for Apple are exact matches across Path A and Path B
    exact_matches = [r for r in results if r.status == "exact_match"]
    assert len(exact_matches) == 10
    for m in exact_matches:
        assert m.difference == 0.0
        assert m.company_facts_value is not None
        assert m.ixbrl_value is not None
        assert m.company_facts_value == m.ixbrl_value

    # Persist reconciliations to SQLite
    recon_repo = ReconciliationRepository()
    recon_repo.delete_reconciliations_by_accession(accn)
    recon_repo.save_reconciliations(results)

    persisted = recon_repo.get_reconciliations_by_accession(accn)
    assert len(persisted) == 10

    # Custom concept analysis
    mapper = SemanticMapper()
    custom_candidates = mapper.extract_custom_candidates_from_facts(accn, ix_facts)
    assert len(custom_candidates) > 0
    recon_repo.delete_custom_candidates_by_accession(accn)
    recon_repo.save_custom_candidates(custom_candidates)
    db_custom = recon_repo.get_custom_candidates_by_accession(accn)
    assert len(db_custom) == len(custom_candidates)

    # Segment classification
    classifier = SegmentClassifier()
    seg_report = classifier.classify_segments(accn, ix_facts)
    assert seg_report.total_segment_facts > 300
    assert len(seg_report.unique_axes) > 0

