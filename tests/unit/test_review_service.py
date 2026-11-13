import math
from unittest.mock import MagicMock, patch
import pytest

from app.api.schemas.review import SubmitReviewRequest
from app.database.repositories.fact_repository import FactRecord
from app.database.repositories.review_repository import ReviewRecord, ReviewRepository
from app.review.idempotency import IdempotencyManager, generate_idempotency_key
from app.review.service import ReviewService


@pytest.fixture
def mock_repos():
    review_repo = MagicMock(spec=ReviewRepository)
    fact_repo = MagicMock()
    filing_repo = MagicMock()
    scoring_repo = MagicMock()
    val_repo = MagicMock()
    val_engine = MagicMock()
    wf_service = MagicMock()

    # Default repo setups
    review_repo.get_by_idempotency_key.return_value = None
    review_repo.get_latest_review_round.return_value = 0
    review_repo.get_reviews_by_accession.return_value = []
    review_repo.save_review.side_effect = lambda r: r

    service = ReviewService(
        review_repo=review_repo,
        fact_repo=fact_repo,
        filing_repo=filing_repo,
        scoring_repo=scoring_repo,
        validation_repo=val_repo,
        validation_engine=val_engine,
        workflow_service=wf_service,
    )
    return service, review_repo, fact_repo, val_repo, val_engine, wf_service


def test_submit_approval_recorded(mock_repos):
    """Test 1: Review approval is recorded accurately with reviewer attribution."""
    service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

    # Setup fact
    fact = MagicMock(spec=FactRecord, raw_value=1000000.0, canonical_name="Total Revenue", unit="USD")
    fact.metric_id = "revenue"
    fact.raw_value = 1000000.0
    fact.canonical_name = "Total Revenue"
    fact.unit = "USD"
    fact_repo.get_selected_facts_by_accession.return_value = [fact]

    req = SubmitReviewRequest(
        accession_number="0000320193-26-000026",
        metric_id="revenue",
        decision="APPROVED",
        reviewer_id="lead_auditor_jane",
        comment="Confirmed against revenue disclosure note 2.",
    )

    res = service.submit_review(req)

    assert res.decision == "APPROVED"
    assert res.reviewer_id == "lead_auditor_jane"
    assert res.original_value == 1000000.0
    assert res.corrected_value is None
    assert res.is_duplicate is False
    assert review_repo.save_review.called


def test_submit_correction_preserves_original_and_reruns_validation(mock_repos):
    """Test 2 & 3: Review correction preserves original value and re-evaluates validation rules."""
    service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

    fact = MagicMock(spec=FactRecord)
    fact.metric_id = "stockholders_equity"
    fact.raw_value = 50000000.0
    fact.canonical_name = "Stockholders Equity"
    fact.unit = "USD"
    fact_repo.get_selected_facts_by_accession.return_value = [fact]

    # No prior corrections for this filing
    review_repo.get_reviews_by_accession.return_value = []

    val_repo.get_validation_summary.side_effect = [
        {"total_rules": 4, "passed": 3, "failed": 1, "warnings": 0, "not_evaluated": 0},  # before
        {"total_rules": 4, "passed": 4, "failed": 0, "warnings": 0, "not_evaluated": 0},  # after
    ]

    req = SubmitReviewRequest(
        accession_number="0000320193-26-000026",
        metric_id="stockholders_equity",
        decision="CORRECTED",
        reviewer_id="senior_accountant_bob",
        comment="Corrected based on consolidated balance sheet ending equity line.",
        corrected_value=65000000.0,
        unit="USD",
        evidence_used="Balance Sheet, Page 45",
    )

    res = service.submit_review(req)

    assert res.decision == "CORRECTED"
    assert res.original_value == 50000000.0  # Original preserved
    assert res.corrected_value == 65000000.0  # Corrected stored separately
    assert res.previous_validation_status == "FAIL"
    assert res.new_validation_status == "PASS"

    # Verify validation engine re-run with consolidated overrides
    val_engine.validate_filing.assert_called_once_with(
        accession_number="0000320193-26-000026",
        fact_overrides={"stockholders_equity": 65000000.0},
        persist=True,
    )


def test_submit_rejection_marks_unresolved(mock_repos):
    """Test 4: Rejection records reviewer finding and leaves metric unverified."""
    service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

    fact = MagicMock(spec=FactRecord)
    fact.metric_id = "operating_income"
    fact.raw_value = 250000.0
    fact.canonical_name = "Operating Income"
    fact.unit = "USD"
    fact_repo.get_selected_facts_by_accession.return_value = [fact]

    req = SubmitReviewRequest(
        accession_number="0000320193-26-000026",
        metric_id="operating_income",
        decision="REJECTED",
        reviewer_id="audit_manager_sarah",
        comment="Cannot reconcile single-step operating presentation with disclosure.",
    )

    res = service.submit_review(req)

    assert res.decision == "REJECTED"
    assert res.original_value == 250000.0
    assert res.corrected_value is None
    assert val_engine.validate_filing.called is False


def test_invalid_correction_values_rejected(mock_repos):
    """Test 5: Non-numeric, missing, or NaN correction values are strictly rejected."""
    service, _, _, _, _, _ = mock_repos

    # Missing corrected_value
    req1 = SubmitReviewRequest(
        accession_number="test-accn",
        metric_id="revenue",
        decision="CORRECTED",
        reviewer_id="auditor",
        comment="Forgot value",
        corrected_value=None,
    )
    with pytest.raises(ValueError, match="numeric 'corrected_value' must be provided"):
        service.submit_review(req1)

    # NaN corrected_value
    req2 = SubmitReviewRequest(
        accession_number="test-accn",
        metric_id="revenue",
        decision="CORRECTED",
        reviewer_id="auditor",
        comment="NaN value",
        corrected_value=float("nan"),
    )
    with pytest.raises(ValueError, match="Must be a finite number"):
        service.submit_review(req2)


def test_automated_actor_rejected(mock_repos):
    """Test 6: Automated actors / missing reviewer ID are blocked from approving financial values."""
    service, _, _, _, _, _ = mock_repos

    for forbidden in ["", "  ", "ai", "llm", "bot", "system", "auto"]:
        req = SubmitReviewRequest(
            accession_number="test-accn",
            metric_id="revenue",
            decision="APPROVED",
            reviewer_id=forbidden,
            comment="Approved automatically",
        )
        with pytest.raises(ValueError):
            service.submit_review(req)


def test_duplicate_review_prevented_by_idempotency_key(mock_repos):
    """Test 7: Submitting duplicate review with identical idempotency key returns existing record without side effects."""
    service, review_repo, _, _, val_engine, _ = mock_repos

    existing = ReviewRecord(
        id=42,
        review_id="rev_existing_123",
        accession_number="test-accn",
        thread_id="thread_test",
        metric_id="revenue",
        canonical_name="Revenue",
        review_round=1,
        reviewer_id="lead_auditor",
        decision="APPROVED",
        original_value=500.0,
        comment="First submission",
        idempotency_key="idemp_unique_key_111",
        created_at="2026-01-01T00:00:00Z",
    )
    review_repo.get_by_idempotency_key.return_value = existing

    req = SubmitReviewRequest(
        accession_number="test-accn",
        metric_id="revenue",
        decision="APPROVED",
        reviewer_id="lead_auditor",
        comment="Duplicate attempt",
        idempotency_key="idemp_unique_key_111",
    )

    res = service.submit_review(req)

    assert res.is_duplicate is True
    assert res.review_id == "rev_existing_123"
    assert res.decision == "APPROVED"
    # Ensure no new record was saved and no re-validation run
    assert review_repo.save_review.called is False
    assert val_engine.validate_filing.called is False


def test_review_resumes_paused_workflow(mock_repos):
    """Test 8: Review submission resumes paused LangGraph workflow."""
    service, _, _, _, _, wf_service = mock_repos

    wf_service.get_workflow_state.return_value = {
        "thread_id": "thread_test_paused",
        "is_paused_for_review": True,
        "values": {"workflow_status": "PAUSED_FOR_REVIEW"},
    }

    req = SubmitReviewRequest(
        accession_number="0000320193-26-000026",
        thread_id="thread_test_paused",
        metric_id="total_assets",
        decision="APPROVED",
        reviewer_id="auditor_lead",
        comment="Reviewed assets note.",
    )

    res = service.submit_review(req)

    assert res.decision == "APPROVED"
    wf_service.resume_workflow.assert_called_once_with(
        thread_id="thread_test_paused",
        decision="APPROVED",
        reviewer_id="auditor_lead",
        decision_notes="Reviewed assets note.",
        corrected_values=None,
    )



# ============================================================================
# BUG-01 Tests: test_review_ui_payload
# ============================================================================


class TestReviewUIPayload:
    """BUG-01: SubmitReviewResponse schema includes revalidation_summary and UI handles it safely."""

    def test_response_accepts_valid_revalidation_summary(self):
        """SubmitReviewResponse accepts a valid revalidation_summary dict."""
        from app.api.schemas.review import SubmitReviewResponse

        resp = SubmitReviewResponse(
            review_id="rev_001",
            accession_number="0000320193-26-000026",
            reviewer_id="auditor",
            decision="CORRECTED",
            comment="Fixed",
            idempotency_key="key_001",
            revalidation_summary={"total_rules": 5, "passed": 4, "failed": 1, "warnings": 0, "not_evaluated": 0},
        )
        assert resp.revalidation_summary is not None
        assert resp.revalidation_summary["passed"] == 4
        assert resp.revalidation_summary["failed"] == 1

    def test_response_accepts_none_revalidation_summary(self):
        """SubmitReviewResponse accepts None when summary is unavailable."""
        from app.api.schemas.review import SubmitReviewResponse

        resp = SubmitReviewResponse(
            review_id="rev_002",
            accession_number="0000320193-26-000026",
            reviewer_id="auditor",
            decision="APPROVED",
            comment="OK",
            idempotency_key="key_002",
            revalidation_summary=None,
        )
        assert resp.revalidation_summary is None

    def test_response_default_revalidation_summary_is_none(self):
        """SubmitReviewResponse defaults revalidation_summary to None when omitted."""
        from app.api.schemas.review import SubmitReviewResponse

        resp = SubmitReviewResponse(
            review_id="rev_003",
            accession_number="0000320193-26-000026",
            reviewer_id="auditor",
            decision="APPROVED",
            comment="OK",
            idempotency_key="key_003",
        )
        assert resp.revalidation_summary is None

    def test_getattr_safe_access_on_response(self):
        """getattr() fallback works safely for UI access pattern."""
        from app.api.schemas.review import SubmitReviewResponse

        resp = SubmitReviewResponse(
            review_id="rev_004",
            accession_number="0000320193-26-000026",
            reviewer_id="auditor",
            decision="APPROVED",
            comment="OK",
            idempotency_key="key_004",
        )
        reval = getattr(resp, "revalidation_summary", None)
        assert reval is None  # No crash, returns None

    def test_correction_response_includes_revalidation_summary(self, mock_repos):
        """Service returns revalidation_summary in response when correction triggers revalidation."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "revenue"
        fact.raw_value = 500.0
        fact.canonical_name = "Revenue"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]
        review_repo.get_reviews_by_accession.return_value = []

        expected_summary = {"total_rules": 3, "passed": 3, "failed": 0, "warnings": 0, "not_evaluated": 0}
        val_repo.get_validation_summary.side_effect = [
            {"total_rules": 3, "passed": 2, "failed": 1, "warnings": 0, "not_evaluated": 0},  # before
            expected_summary,  # after
        ]

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="revenue",
            decision="CORRECTED",
            reviewer_id="auditor_jane",
            comment="Corrected revenue.",
            corrected_value=600.0,
        )

        res = service.submit_review(req)
        assert res.revalidation_summary == expected_summary

    def test_approval_response_has_none_revalidation_summary(self, mock_repos):
        """Approval without prior corrections returns revalidation_summary=None."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "revenue"
        fact.raw_value = 500.0
        fact.canonical_name = "Revenue"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]
        review_repo.get_reviews_by_accession.return_value = []

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="revenue",
            decision="APPROVED",
            reviewer_id="auditor_jane",
            comment="Looks correct.",
        )

        res = service.submit_review(req)
        assert res.revalidation_summary is None


# ============================================================================
# BUG-02 Tests: test_multi_correction_preservation
# ============================================================================


class TestMultiCorrectionPreservation:
    """BUG-02: Multiple consecutive corrections are all preserved in validation overrides."""

    def _make_correction_review(self, metric_id: str, corrected_value: float, round_num: int = 1) -> ReviewRecord:
        """Helper to create a mock CORRECTED ReviewRecord."""
        return ReviewRecord(
            review_id=f"rev_{metric_id}_{round_num}",
            accession_number="0000320193-26-000026",
            metric_id=metric_id,
            canonical_name=metric_id.replace("_", " ").title(),
            review_round=round_num,
            reviewer_id="auditor",
            decision="CORRECTED",
            original_value=0.0,
            corrected_value=corrected_value,
            comment="Correction",
            idempotency_key=f"key_{metric_id}_{round_num}",
            created_at=f"2026-01-01T00:0{round_num}:00Z",
        )

    def test_single_correction(self, mock_repos):
        """One correction produces single-metric overrides."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "total_assets"
        fact.raw_value = 1000.0
        fact.canonical_name = "Total Assets"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]
        review_repo.get_reviews_by_accession.return_value = []
        val_repo.get_validation_summary.side_effect = [
            {"total_rules": 4, "passed": 3, "failed": 1, "warnings": 0, "not_evaluated": 0},
            {"total_rules": 4, "passed": 4, "failed": 0, "warnings": 0, "not_evaluated": 0},
        ]

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="total_assets",
            decision="CORRECTED",
            reviewer_id="auditor",
            comment="Corrected total assets.",
            corrected_value=1200.0,
        )
        service.submit_review(req)

        val_engine.validate_filing.assert_called_once_with(
            accession_number="0000320193-26-000026",
            fact_overrides={"total_assets": 1200.0},
            persist=True,
        )

    def test_two_consecutive_corrections(self, mock_repos):
        """Two corrections: second call receives both overrides."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        # First correction already stored
        prior_review = self._make_correction_review("total_assets", 1200.0, round_num=1)

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "revenue"
        fact.raw_value = 500.0
        fact.canonical_name = "Revenue"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]

        # When submitting revenue correction, prior reviews include total_assets correction
        review_repo.get_reviews_by_accession.return_value = [prior_review]
        val_repo.get_validation_summary.side_effect = [
            {"total_rules": 4, "passed": 2, "failed": 2, "warnings": 0, "not_evaluated": 0},
            {"total_rules": 4, "passed": 4, "failed": 0, "warnings": 0, "not_evaluated": 0},
        ]

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="revenue",
            decision="CORRECTED",
            reviewer_id="auditor",
            comment="Corrected revenue.",
            corrected_value=600.0,
        )
        service.submit_review(req)

        val_engine.validate_filing.assert_called_once_with(
            accession_number="0000320193-26-000026",
            fact_overrides={"total_assets": 1200.0, "revenue": 600.0},
            persist=True,
        )

    def test_three_consecutive_corrections_spec_scenario(self, mock_repos):
        """Critical scenario from spec: three corrections all preserved."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        # Two prior corrections already stored
        prior_reviews = [
            self._make_correction_review("total_assets", 1200.0, round_num=1),
            self._make_correction_review("revenue", 600.0, round_num=2),
        ]

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "net_income"
        fact.raw_value = 100.0
        fact.canonical_name = "Net Income"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]

        review_repo.get_reviews_by_accession.return_value = prior_reviews
        val_repo.get_validation_summary.side_effect = [
            {"total_rules": 5, "passed": 2, "failed": 3, "warnings": 0, "not_evaluated": 0},
            {"total_rules": 5, "passed": 5, "failed": 0, "warnings": 0, "not_evaluated": 0},
        ]

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="net_income",
            decision="CORRECTED",
            reviewer_id="auditor",
            comment="Corrected net income.",
            corrected_value=150.0,
        )
        service.submit_review(req)

        # All three corrections must be present in the overrides
        val_engine.validate_filing.assert_called_once_with(
            accession_number="0000320193-26-000026",
            fact_overrides={"total_assets": 1200.0, "revenue": 600.0, "net_income": 150.0},
            persist=True,
        )

    def test_correcting_same_metric_twice_latest_wins(self, mock_repos):
        """Correcting the same metric twice: latest value takes precedence."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        # First correction for revenue was 550, now submitting 600
        prior_review = self._make_correction_review("revenue", 550.0, round_num=1)

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "revenue"
        fact.raw_value = 500.0
        fact.canonical_name = "Revenue"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]

        review_repo.get_reviews_by_accession.return_value = [prior_review]
        val_repo.get_validation_summary.side_effect = [
            {"total_rules": 3, "passed": 2, "failed": 1, "warnings": 0, "not_evaluated": 0},
            {"total_rules": 3, "passed": 3, "failed": 0, "warnings": 0, "not_evaluated": 0},
        ]

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="revenue",
            decision="CORRECTED",
            reviewer_id="auditor",
            comment="Second correction for revenue.",
            corrected_value=600.0,
        )
        service.submit_review(req)

        val_engine.validate_filing.assert_called_once_with(
            accession_number="0000320193-26-000026",
            fact_overrides={"revenue": 600.0},  # Latest wins
            persist=True,
        )

    def test_rejected_corrections_excluded(self, mock_repos):
        """Rejected corrections are excluded from active overrides."""
        service, _, _, _, _, _ = mock_repos

        # revenue was corrected to 600, then REJECTED
        reviews = [
            self._make_correction_review("revenue", 600.0, round_num=1),
            ReviewRecord(
                review_id="rev_revenue_rejected",
                accession_number="0000320193-26-000026",
                metric_id="revenue",
                canonical_name="Revenue",
                review_round=2,
                reviewer_id="auditor",
                decision="REJECTED",
                original_value=500.0,
                comment="Rejecting prior correction.",
                idempotency_key="key_rej_1",
                created_at="2026-01-01T00:03:00Z",
            ),
            self._make_correction_review("total_assets", 1200.0, round_num=3),
        ]
        service.review_repo.get_reviews_by_accession.return_value = reviews

        active = service.get_active_corrections_for_filing("0000320193-26-000026")
        assert "revenue" not in active  # Rejected
        assert active == {"total_assets": 1200.0}

    def test_corrections_isolated_between_filings(self, mock_repos):
        """Corrections from one filing do not affect another filing."""
        service, _, _, _, _, _ = mock_repos

        # Filing A has a correction
        reviews_a = [self._make_correction_review("revenue", 600.0)]
        # Filing B has no corrections
        reviews_b = []

        service.review_repo.get_reviews_by_accession.side_effect = lambda accn: (
            reviews_a if accn == "FILING-A" else reviews_b
        )

        active_a = service.get_active_corrections_for_filing("FILING-A")
        active_b = service.get_active_corrections_for_filing("FILING-B")

        assert active_a == {"revenue": 600.0}
        assert active_b == {}

    def test_original_values_unchanged_after_correction(self, mock_repos):
        """Original extracted values remain unchanged in the response."""
        service, review_repo, fact_repo, val_repo, val_engine, wf_service = mock_repos

        fact = MagicMock(spec=FactRecord)
        fact.metric_id = "revenue"
        fact.raw_value = 500.0
        fact.canonical_name = "Revenue"
        fact.unit = "USD"
        fact_repo.get_selected_facts_by_accession.return_value = [fact]
        review_repo.get_reviews_by_accession.return_value = []
        val_repo.get_validation_summary.side_effect = [
            {"total_rules": 3, "passed": 2, "failed": 1, "warnings": 0, "not_evaluated": 0},
            {"total_rules": 3, "passed": 3, "failed": 0, "warnings": 0, "not_evaluated": 0},
        ]

        req = SubmitReviewRequest(
            accession_number="0000320193-26-000026",
            metric_id="revenue",
            decision="CORRECTED",
            reviewer_id="auditor",
            comment="Correcting revenue.",
            corrected_value=600.0,
        )
        res = service.submit_review(req)

        # Original value preserved, corrected stored separately
        assert res.original_value == 500.0
        assert res.corrected_value == 600.0

    def test_get_active_corrections_returns_full_consolidated_dict(self, mock_repos):
        """Validation receives the full consolidated override dictionary."""
        service, _, _, _, _, _ = mock_repos

        reviews = [
            self._make_correction_review("total_assets", 1200.0, round_num=1),
            self._make_correction_review("revenue", 600.0, round_num=2),
            self._make_correction_review("net_income", 150.0, round_num=3),
        ]
        service.review_repo.get_reviews_by_accession.return_value = reviews

        active = service.get_active_corrections_for_filing("0000320193-26-000026")
        assert active == {"total_assets": 1200.0, "revenue": 600.0, "net_income": 150.0}
