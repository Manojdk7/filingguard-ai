import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.workflow.checkpointer import get_checkpointer
from app.workflow.graph import build_workflow_graph, compile_workflow_graph
from app.workflow.nodes import extract_node
from app.workflow.resume import WorkflowService
from app.workflow.state import FilingWorkflowState, ReviewDecision, ReviewRequirement


@pytest.fixture
def temp_checkpointer():
    """Create an isolated, temporary SQLite checkpointer for unit testing."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_checkpoints.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    yield saver, db_path
    try:
        conn.close()
    except Exception:
        pass
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_typed_workflow_state_structure():
    """Test 1: Typed workflow state satisfies required keys and typing."""
    state: FilingWorkflowState = {
        "workflow_id": "wf_test_001",
        "thread_id": "thread_test_001",
        "accession_number": "0000320193-26-000026",
        "cik": "0000320193",
        "current_stage": "init",
        "workflow_status": "RUNNING",
        "errors": [],
        "execution_log": ["Initialized"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    assert state["workflow_id"] == "wf_test_001"
    assert state["workflow_status"] == "RUNNING"
    assert len(state["errors"]) == 0


def test_extract_node_uses_existing_metric_extractor_api():
    accession_number = "test-extraction-accn"
    cik = "0000320193"
    state = {
        "accession_number": accession_number,
        "cik": cik,
        "errors": [],
        "execution_log": [],
    }

    with patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.MetricExtractor") as mock_extractor, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository"):
        mock_fact_repo.return_value.get_selected_facts_by_accession.side_effect = [
            [],
            [MagicMock()],
        ]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = []
        mock_doc_repo.return_value.get_by_accession.return_value = None
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []

        result = extract_node(state)

    mock_extractor.return_value.extract_metrics_for_filing.assert_called_once_with(
        cik,
        accession_number=accession_number,
    )
    assert result["extraction_result"]["status"] == "success"
    assert result["extraction_result"]["company_facts_count"] == 1


def test_extract_node_parses_inline_xbrl_through_parser_api():
    accession_number = "0001652044-26-000018"
    cik = "0001652044"
    parsed_fact = MagicMock()
    parsed_fact.is_custom = False
    parsing_summary = MagicMock(total_facts=1)
    document = MagicMock(
        local_path="data/filings/google.htm",
        sha256_hash="document-hash",
        source_url="https://www.sec.gov/Archives/filing/google.htm",
    )
    state = {
        "accession_number": accession_number,
        "cik": cik,
        "errors": [],
        "execution_log": [],
    }

    with patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.InlineXBRLParser") as mock_parser, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository"):
        mock_fact_repo.return_value.get_selected_facts_by_accession.return_value = [
            MagicMock()
        ]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = []
        mock_doc_repo.return_value.get_by_accession.return_value = document
        mock_parser.return_value.parse_document.return_value = (
            [parsed_fact],
            parsing_summary,
        )
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []

        result = extract_node(state)

    mock_parser.return_value.parse_document.assert_called_once_with(
        local_file_path=document.local_path,
        accession_number=accession_number,
        source_doc_hash=document.sha256_hash,
        source_url=document.source_url,
    )
    mock_xbrl_repo.return_value.save_facts.assert_called_once_with([parsed_fact])
    assert result["extraction_result"]["ixbrl_facts_count"] == 1
    assert not result["errors"]


def test_successful_end_to_end_graph_execution(temp_checkpointer):
    """Test 2: Successful end-to-end graph execution with auto-pass completion."""
    saver, _ = temp_checkpointer

    with patch("app.workflow.nodes.FilingRepository") as mock_filing_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository") as mock_recon_repo, \
         patch("app.workflow.nodes.SemanticMapper") as mock_semantic_mapper, \
         patch("app.workflow.nodes.ConfidenceScoringEngine") as mock_scoring_engine, \
         patch("app.workflow.nodes.FinancialValidationEngine") as mock_val_engine, \
         patch("app.workflow.nodes.ValidationRepository") as mock_val_repo:

        # Mock filing & document
        mock_filing = MagicMock(
            accession_number="test-accn",
            cik="0000320193",
            company_name="Test Corp",
            ticker="TST",
            form_type="10-K",
            report_period="2026-09-26",
            primary_document="test.htm",
            primary_doc_url="https://sec.gov/test.htm",
        )
        mock_filing_repo.return_value.get_by_accession.return_value = mock_filing
        mock_doc_repo.return_value.get_by_accession.return_value = MagicMock(
            local_path="test.htm", sha256_hash="hash", file_size_bytes=1000
        )

        # Mock facts
        mock_fact_repo.return_value.get_selected_facts_by_accession.return_value = [MagicMock()]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = [MagicMock()]
        mock_recon_service.return_value.reconcile_filing.return_value = []
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []
        mock_recon_repo.return_value.save_reconciliations.return_value = None
        mock_recon_repo.return_value.save_custom_candidates.return_value = None
        mock_semantic_mapper.return_value.extract_custom_candidates_from_facts.return_value = []

        # Mock scoring engine (AUTO_PASS)
        mock_filing_score = MagicMock(
            overall_score=0.98,
            overall_status="HIGH",
            overall_review_category="AUTO_PASS",
            metrics_assessed_count=10,
            metrics_missing_count=0,
            critical_metrics_present=True,
            reduction_reasons=[],
        )
        mock_scoring_engine.return_value.score_filing.return_value = (mock_filing_score, [])

        # Mock validation engine (All passed)
        mock_val_engine.return_value.validate_filing.return_value = [
            MagicMock(status="PASS", rule_name="Accounting Equation")
        ]
        mock_val_repo.return_value.get_validation_summary.return_value = {
            "total_rules": 1, "passed": 1, "failed": 0, "warnings": 0, "not_evaluated": 0
        }

        service = WorkflowService(checkpointer=saver)
        t_id, final_state = service.start_workflow("test-accn", cik="0000320193")

        assert final_state["workflow_status"] == "COMPLETED"
        assert final_state["current_stage"] == "completed"
        assert final_state["review_requirements"]["required"] is False
        assert len(final_state["errors"]) == 0


def test_sec_retrieval_failure_handling(temp_checkpointer):
    """Test 3: Retrieval error halts pipeline with structured failure."""
    saver, _ = temp_checkpointer

    with patch("app.workflow.nodes.FilingRepository") as mock_filing_repo:
        mock_filing_repo.return_value.get_by_accession.return_value = None

        service = WorkflowService(checkpointer=saver)
        t_id, final_state = service.start_workflow("non-existent-accn")

        assert final_state["workflow_status"] == "FAILED"
        assert len(final_state["errors"]) > 0
        assert "Retrieve" in final_state["errors"][0] or "not be located" in final_state["errors"][0]


def test_scoring_mandatory_review_interruption(temp_checkpointer):
    """Test 5 & 8: Scoring mandatory-review trigger halts at review gate and interrupts."""
    saver, _ = temp_checkpointer

    with patch("app.workflow.nodes.FilingRepository") as mock_filing_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository") as mock_recon_repo, \
         patch("app.workflow.nodes.SemanticMapper") as mock_semantic_mapper, \
         patch("app.workflow.nodes.ConfidenceScoringEngine") as mock_scoring_engine, \
         patch("app.workflow.nodes.FinancialValidationEngine") as mock_val_engine, \
         patch("app.workflow.nodes.ValidationRepository") as mock_val_repo:

        mock_filing = MagicMock(
            accession_number="test-accn-mandatory",
            cik="0000320193",
            company_name="Test Corp",
            ticker="TST",
            form_type="10-K",
            report_period="2026-09-26",
            primary_document="test.htm",
            primary_doc_url="https://sec.gov/test.htm",
        )
        mock_filing_repo.return_value.get_by_accession.return_value = mock_filing
        mock_doc_repo.return_value.get_by_accession.return_value = MagicMock(
            local_path="test.htm", sha256_hash="hash", file_size_bytes=1000
        )
        mock_fact_repo.return_value.get_selected_facts_by_accession.return_value = [MagicMock()]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = [MagicMock()]
        mock_recon_service.return_value.reconcile_filing.return_value = []
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []
        mock_recon_repo.return_value.save_reconciliations.return_value = None
        mock_recon_repo.return_value.save_custom_candidates.return_value = None
        mock_semantic_mapper.return_value.extract_custom_candidates_from_facts.return_value = []

        # MANDATORY_REVIEW triggered
        mock_filing_score = MagicMock(
            overall_score=0.72,
            overall_status="MEDIUM",
            overall_review_category="MANDATORY_REVIEW",
            metrics_assessed_count=9,
            metrics_missing_count=1,
            critical_metrics_present=False,
            reduction_reasons=["Missing critical metric: Total Liabilities"],
        )
        mock_scoring_engine.return_value.score_filing.return_value = (mock_filing_score, [])

        mock_val_engine.return_value.validate_filing.return_value = []
        mock_val_repo.return_value.get_validation_summary.return_value = {
            "total_rules": 0, "passed": 0, "failed": 0, "warnings": 0, "not_evaluated": 0
        }

        service = WorkflowService(checkpointer=saver)
        thread_id = "thread_mandatory_review"
        t_id, state = service.start_workflow("test-accn-mandatory", thread_id=thread_id)

        # Verify workflow is paused for review
        status = service.get_workflow_state(thread_id)
        assert status is not None
        assert status["is_paused_for_review"] is True
        assert state["workflow_status"] == "PAUSED_FOR_REVIEW"
        assert state["review_requirements"]["required"] is True
        assert len(state["review_requirements"]["reasons"]) > 0


def test_human_review_approval_and_resume(temp_checkpointer):
    """Test 9 & 11: Human review approval resumes workflow to COMPLETED."""
    saver, _ = temp_checkpointer

    with patch("app.workflow.nodes.FilingRepository") as mock_filing_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository") as mock_recon_repo, \
         patch("app.workflow.nodes.SemanticMapper") as mock_semantic_mapper, \
         patch("app.workflow.nodes.ConfidenceScoringEngine") as mock_scoring_engine, \
         patch("app.workflow.nodes.FinancialValidationEngine") as mock_val_engine, \
         patch("app.workflow.nodes.ValidationRepository") as mock_val_repo:

        mock_filing = MagicMock(
            accession_number="test-accn-review-app",
            cik="0000320193",
            company_name="Test Corp",
            ticker="TST",
            form_type="10-K",
            report_period="2026-09-26",
            primary_document="test.htm",
            primary_doc_url="https://sec.gov/test.htm",
        )
        mock_filing_repo.return_value.get_by_accession.return_value = mock_filing
        mock_doc_repo.return_value.get_by_accession.return_value = MagicMock(
            local_path="test.htm", sha256_hash="hash", file_size_bytes=1000
        )
        mock_fact_repo.return_value.get_selected_facts_by_accession.return_value = [MagicMock()]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = [MagicMock()]
        mock_recon_service.return_value.reconcile_filing.return_value = []
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []
        mock_recon_repo.return_value.save_reconciliations.return_value = None
        mock_recon_repo.return_value.save_custom_candidates.return_value = None
        mock_semantic_mapper.return_value.extract_custom_candidates_from_facts.return_value = []

        mock_filing_score = MagicMock(
            overall_score=0.75,
            overall_status="MEDIUM",
            overall_review_category="MANDATORY_REVIEW",
            metrics_assessed_count=10,
            metrics_missing_count=0,
            critical_metrics_present=True,
            reduction_reasons=["Disclosed under single-step income statement"],
        )
        mock_scoring_engine.return_value.score_filing.return_value = (mock_filing_score, [])
        mock_val_engine.return_value.validate_filing.return_value = []
        mock_val_repo.return_value.get_validation_summary.return_value = {
            "total_rules": 0, "passed": 0, "failed": 0, "warnings": 0, "not_evaluated": 0
        }

        service = WorkflowService(checkpointer=saver)
        thread_id = "thread_review_app"
        service.start_workflow("test-accn-review-app", thread_id=thread_id)

        # Resume with APPROVED
        resumed = service.resume_workflow(
            thread_id=thread_id,
            decision="APPROVED",
            reviewer_id="lead_auditor",
            decision_notes="Confirmed disclosure in note 4.",
        )

        assert resumed["workflow_status"] == "COMPLETED"
        assert resumed["review_decisions"]["decision"] == "APPROVED"
        assert resumed["review_decisions"]["reviewer_id"] == "lead_auditor"


def test_human_review_rejection_and_resume(temp_checkpointer):
    """Test 10: Human review rejection resumes workflow to REJECTED."""
    saver, _ = temp_checkpointer

    with patch("app.workflow.nodes.FilingRepository") as mock_filing_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository") as mock_recon_repo, \
         patch("app.workflow.nodes.SemanticMapper") as mock_semantic_mapper, \
         patch("app.workflow.nodes.ConfidenceScoringEngine") as mock_scoring_engine, \
         patch("app.workflow.nodes.FinancialValidationEngine") as mock_val_engine, \
         patch("app.workflow.nodes.ValidationRepository") as mock_val_repo:

        mock_filing = MagicMock(
            accession_number="test-accn-review-rej",
            cik="0000320193",
            company_name="Test Corp",
            ticker="TST",
            form_type="10-K",
            report_period="2026-09-26",
            primary_document="test.htm",
            primary_doc_url="https://sec.gov/test.htm",
        )
        mock_filing_repo.return_value.get_by_accession.return_value = mock_filing
        mock_doc_repo.return_value.get_by_accession.return_value = MagicMock(
            local_path="test.htm", sha256_hash="hash", file_size_bytes=1000
        )
        mock_fact_repo.return_value.get_selected_facts_by_accession.return_value = [MagicMock()]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = [MagicMock()]
        mock_recon_service.return_value.reconcile_filing.return_value = []
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []
        mock_recon_repo.return_value.save_reconciliations.return_value = None
        mock_recon_repo.return_value.save_custom_candidates.return_value = None
        mock_semantic_mapper.return_value.extract_custom_candidates_from_facts.return_value = []

        mock_filing_score = MagicMock(
            overall_score=0.50,
            overall_status="LOW",
            overall_review_category="MANDATORY_REVIEW",
            metrics_assessed_count=5,
            metrics_missing_count=5,
            critical_metrics_present=False,
            reduction_reasons=["Major disclosure omissions"],
        )
        mock_scoring_engine.return_value.score_filing.return_value = (mock_filing_score, [])
        mock_val_engine.return_value.validate_filing.return_value = []
        mock_val_repo.return_value.get_validation_summary.return_value = {
            "total_rules": 0, "passed": 0, "failed": 0, "warnings": 0, "not_evaluated": 0
        }

        service = WorkflowService(checkpointer=saver)
        thread_id = "thread_review_rej"
        service.start_workflow("test-accn-review-rej", thread_id=thread_id)

        # Resume with REJECTED
        resumed = service.resume_workflow(
            thread_id=thread_id,
            decision="REJECTED",
            reviewer_id="compliance_officer",
            decision_notes="Cannot verify missing statements.",
        )

        assert resumed["workflow_status"] == "REJECTED"
        assert resumed["review_decisions"]["decision"] == "REJECTED"


def test_sqlite_checkpoint_persistence_and_restart(temp_checkpointer):
    """Test 12 & 13: SQLite checkpoint persistence survives process / service restart."""
    saver, db_path = temp_checkpointer

    with patch("app.workflow.nodes.FilingRepository") as mock_filing_repo, \
         patch("app.workflow.nodes.DocumentRepository") as mock_doc_repo, \
         patch("app.workflow.nodes.FactRepository") as mock_fact_repo, \
         patch("app.workflow.nodes.XBRLFactRepository") as mock_xbrl_repo, \
         patch("app.workflow.nodes.CrossSourceReconciliationService") as mock_recon_service, \
         patch("app.workflow.nodes.ReconciliationRepository") as mock_recon_repo, \
         patch("app.workflow.nodes.SemanticMapper") as mock_semantic_mapper, \
         patch("app.workflow.nodes.ConfidenceScoringEngine") as mock_scoring_engine, \
         patch("app.workflow.nodes.FinancialValidationEngine") as mock_val_engine, \
         patch("app.workflow.nodes.ValidationRepository") as mock_val_repo:

        mock_filing = MagicMock(
            accession_number="test-accn-restart",
            cik="0000320193",
            company_name="Test Corp",
            ticker="TST",
            form_type="10-K",
            report_period="2026-09-26",
            primary_document="test.htm",
            primary_doc_url="https://sec.gov/test.htm",
        )
        mock_filing_repo.return_value.get_by_accession.return_value = mock_filing
        mock_doc_repo.return_value.get_by_accession.return_value = MagicMock(
            local_path="test.htm", sha256_hash="hash", file_size_bytes=1000
        )
        mock_fact_repo.return_value.get_selected_facts_by_accession.return_value = [MagicMock()]
        mock_xbrl_repo.return_value.get_facts_by_accession.return_value = [MagicMock()]
        mock_recon_service.return_value.reconcile_filing.return_value = []
        mock_recon_service.return_value.reconcile_facts_for_filing.return_value = []
        mock_recon_repo.return_value.save_reconciliations.return_value = None
        mock_recon_repo.return_value.save_custom_candidates.return_value = None
        mock_semantic_mapper.return_value.extract_custom_candidates_from_facts.return_value = []

        mock_filing_score = MagicMock(
            overall_score=0.70,
            overall_status="MEDIUM",
            overall_review_category="MANDATORY_REVIEW",
            metrics_assessed_count=10,
            metrics_missing_count=0,
            critical_metrics_present=True,
            reduction_reasons=["Requires review"],
        )
        mock_scoring_engine.return_value.score_filing.return_value = (mock_filing_score, [])
        mock_val_engine.return_value.validate_filing.return_value = []
        mock_val_repo.return_value.get_validation_summary.return_value = {
            "total_rules": 0, "passed": 0, "failed": 0, "warnings": 0, "not_evaluated": 0
        }

        # 1. First service instance runs until interrupt
        thread_id = "thread_restart_test"
        service1 = WorkflowService(checkpointer=saver)
        service1.start_workflow("test-accn-restart", thread_id=thread_id)

        # 2. Simulate process restart: create completely new service and new checkpointer pointing to same file
        conn2 = sqlite3.connect(db_path, check_same_thread=False)
        saver2 = SqliteSaver(conn2)
        service2 = WorkflowService(checkpointer=saver2)

        # 3. Retrieve state after restart
        state_after_restart = service2.get_workflow_state(thread_id)
        assert state_after_restart is not None
        assert state_after_restart["is_paused_for_review"] is True
        assert state_after_restart["values"]["accession_number"] == "test-accn-restart"

        # 4. Resume on restarted service
        resumed = service2.resume_workflow(thread_id, decision="APPROVED")
        assert resumed["workflow_status"] == "COMPLETED"
        conn2.close()


def test_invalid_thread_id_raises_value_error(temp_checkpointer):
    """Test 15: Invalid thread id raises clear error on resume."""
    saver, _ = temp_checkpointer
    service = WorkflowService(checkpointer=saver)

    with pytest.raises(ValueError, match="not found"):
        service.resume_workflow("non-existent-thread-999", decision="APPROVED")



def test_sqlite_checkpointer_connection_management(tmp_path):
    """SYS-02: Verify that checkpointer manages connection lifecycle safely:
    - Reuses managed connection/saver for same db_path without creating duplicate connections.
    - Configures WAL mode, 30s busy timeout, and synchronous=NORMAL.
    - Closes cleanly via close_checkpointer() and close_all_checkpointers().
    - Persists checkpoints and supports workflow resume across re-initialization.
    - Safely handles concurrent readers and serialized checkpoint access under WAL mode."""
    import concurrent.futures
    from app.workflow.checkpointer import (
        get_checkpointer,
        close_checkpointer,
        close_all_checkpointers,
    )

    test_db = tmp_path / "managed_checkpoints.db"

    try:
        # 1. Repeated initialization reuses connection and singleton saver
        saver1 = get_checkpointer(test_db)
        saver2 = get_checkpointer(test_db)
        assert saver1 is saver2, "Expected get_checkpointer to reuse managed singleton saver for identical db_path"

        # 2. Verify PRAGMAs: WAL mode, busy_timeout=30000, synchronous=NORMAL
        conn = saver1.conn
        wal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert wal_mode.lower() == "wal", f"Expected WAL journal mode, got {wal_mode}"

        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert busy_timeout >= 30000, f"Expected busy_timeout >= 30000, got {busy_timeout}"

        sync_mode = conn.execute("PRAGMA synchronous;").fetchone()[0]
        # In SQLite, NORMAL is 1 (or '1')
        assert sync_mode in (1, "1", "NORMAL", "normal")

        # 3. Checkpoint persistence and resume across connection re-initialization
        config = {"configurable": {"thread_id": "thread_managed_test", "checkpoint_ns": ""}}
        checkpoint = {
            "v": 1,
            "id": "chk_001",
            "ts": "2026-01-01T00:00:00Z",
            "channel_values": {"status": "PAUSED_FOR_REVIEW", "accn": "0000320193-26-000001"},
            "channel_versions": {"status": 1, "accn": 1},
            "versions_seen": {},
        }
        saver1.put(config, checkpoint, {}, {})

        # Verify state is written and readable
        tuple_res = saver1.get_tuple(config)
        assert tuple_res is not None
        assert tuple_res.checkpoint["channel_values"]["status"] == "PAUSED_FOR_REVIEW"

        # 4. Connection cleanup
        close_checkpointer(test_db)

        # 5. Reopening connection after cleanup retrieves existing persisted checkpoint
        saver3 = get_checkpointer(test_db)
        assert saver3 is not saver1  # New managed instance after explicit close
        tuple_after_reopen = saver3.get_tuple(config)
        assert tuple_after_reopen is not None
        assert tuple_after_reopen.checkpoint["channel_values"]["status"] == "PAUSED_FOR_REVIEW"

        # 6. Concurrent read and checkpoint access safely handled without locking errors
        def _read_checkpoint(tid: str):
            cfg = {"configurable": {"thread_id": tid, "checkpoint_ns": ""}}
            s = get_checkpointer(test_db)
            return s.get_tuple(cfg)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_read_checkpoint, "thread_managed_test") for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
            assert len(results) == 10
            for r in results:
                assert r is not None
                assert r.checkpoint["channel_values"]["status"] == "PAUSED_FOR_REVIEW"

    finally:
        close_checkpointer(test_db)
        close_all_checkpointers()
