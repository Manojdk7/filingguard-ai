import pytest
from app.extraction.semantic_mapping import SemanticMapper
from app.extraction.reconciliation_service import CrossSourceReconciliationService
from app.extraction.segment_classifier import SegmentClassifier
from app.database.repositories.fact_repository import FactRecord
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact
from app.database.repositories.reconciliation_repository import (
    ReconciliationRepository,
    ReconciliationRecord,
    CustomConceptCandidateRecord,
)


def test_custom_concept_mapping_heuristics():
    mapper = SemanticMapper()

    # 1. Compatible custom revenue extension
    res = mapper.evaluate_custom_concept(
        concept_name="ProductAndServicesRevenueNet",
        namespace="http://example.com/2023",
        period_type="duration",
        unit="USD",
        is_segment=False,
    )
    assert res.is_mapped is True
    assert res.candidate_metric_id == "revenue"
    assert res.confidence_level == "candidate_for_review"

    # 2. Segment-level concept: strictly blocked from consolidated metric mapping
    res_seg = mapper.evaluate_custom_concept(
        concept_name="RetailStoreSalesRevenue",
        namespace="http://example.com/2023",
        period_type="duration",
        unit="USD",
        is_segment=True,
    )
    assert res_seg.is_mapped is False
    assert res_seg.confidence_level == "unresolved"
    assert "segment-level" in res_seg.reason

    # 3. Period type mismatch: instant concept with revenue keyword
    res_inst = mapper.evaluate_custom_concept(
        concept_name="DeferredRevenueNet",
        namespace="http://example.com/2023",
        period_type="instant",  # Revenue requires duration
        unit="USD",
        is_segment=False,
    )
    assert res_inst.is_mapped is False
    assert res_inst.confidence_level == "unresolved"


def test_reconciliation_exact_match():
    service = CrossSourceReconciliationService()

    cf_fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=383285000000.0,
        normalized_value=383285000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Selected fact",
    )

    ix_fact = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
        namespace="http://fasb.org/us-gaap/2023",
        is_custom=False,
        numeric_value=383285000000.0,
        unit="USD",
        context_id="c_fy2023",
        period_type="duration",
        start_date="2022-10-01",
        end_date="2023-09-30",
        is_segment=False,
        dimensions={},
    )

    results = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=[ix_fact],
    )

    rev_recon = next(r for r in results if r.metric_id == "revenue")
    assert rev_recon.status == "exact_match"
    assert rev_recon.difference == 0.0
    assert rev_recon.company_facts_value == 383285000000.0
    assert rev_recon.ixbrl_value == 383285000000.0


def test_reconciliation_value_mismatch():
    service = CrossSourceReconciliationService()

    cf_fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        metric_id="net_income",
        canonical_name="Net Income",
        raw_value=100000000.0,
        normalized_value=100000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="NetIncomeLoss",
        period_type="duration",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Selected",
    )

    ix_fact = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="NetIncomeLoss",
        namespace="http://fasb.org/us-gaap/2023",
        is_custom=False,
        numeric_value=95000000.0,  # 5M difference
        unit="USD",
        context_id="c_fy2023",
        period_type="duration",
        start_date="2022-10-01",
        end_date="2023-09-30",
        is_segment=False,
        dimensions={},
    )

    results = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=[ix_fact],
    )

    ni_recon = next(r for r in results if r.metric_id == "net_income")
    assert ni_recon.status == "value_mismatch"
    assert ni_recon.difference == 5000000.0


def test_reconciliation_period_and_unit_mismatch():
    service = CrossSourceReconciliationService()

    cf_fact = FactRecord(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        metric_id="total_assets",
        canonical_name="Total Assets",
        raw_value=500000000.0,
        normalized_value=500000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="Assets",
        period_type="instant",
        period_start=None,
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Selected",
    )

    # 1. Period mismatch (2022-09-30 instead of 2023-09-30)
    ix_wrong_period = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="Assets",
        namespace="http://fasb.org/us-gaap/2023",
        is_custom=False,
        numeric_value=500000000.0,
        unit="USD",
        context_id="c_prior_instant",
        period_type="instant",
        start_date=None,
        end_date="2022-09-30",
        is_segment=False,
        dimensions={},
    )

    results = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=[ix_wrong_period],
    )
    assert next(r for r in results if r.metric_id == "total_assets").status == "period_mismatch"

    # 2. Unit mismatch (EUR instead of USD)
    ix_wrong_unit = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="Assets",
        namespace="http://fasb.org/us-gaap/2023",
        is_custom=False,
        numeric_value=500000000.0,
        unit="EUR",
        context_id="c_curr_instant",
        period_type="instant",
        start_date=None,
        end_date="2023-09-30",
        is_segment=False,
        dimensions={},
    )
    results2 = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=[ix_wrong_unit],
    )
    assert next(r for r in results2 if r.metric_id == "total_assets").status == "unit_mismatch"


def test_reconciliation_rejects_duration_without_start_date():
    service = CrossSourceReconciliationService()
    accession = "0000320193-23-000106"
    cf_fact = FactRecord(
        cik="0000320193",
        accession_number=accession,
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=100.0,
        normalized_value=100.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Annual fact",
    )
    ix_fact = ParsedXBRLFact(
        accession_number=accession,
        concept_name=cf_fact.concept,
        namespace="http://fasb.org/us-gaap/2023",
        numeric_value=100.0,
        unit="USD",
        context_id="missing-start",
        period_type="duration",
        start_date=None,
        end_date="2023-09-30",
        is_segment=False,
        dimensions={},
    )

    results = service.reconcile_facts_for_filing(
        accession_number=accession,
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=[ix_fact],
    )

    revenue = next(result for result in results if result.metric_id == "revenue")
    assert revenue.status == "not_evaluated"
    assert revenue.difference is None


def test_reconciliation_marks_conflicting_duplicate_facts_ambiguous():
    service = CrossSourceReconciliationService()
    accession = "0000320193-23-000106"
    concept = "RevenueFromContractWithCustomerExcludingAssessedTax"
    cf_fact = FactRecord(
        cik="0000320193",
        accession_number=accession,
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=100.0,
        normalized_value=100.0,
        unit="USD",
        taxonomy="us-gaap",
        concept=concept,
        period_type="duration",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Annual fact",
    )
    ix_facts = [
        ParsedXBRLFact(
            accession_number=accession,
            concept_name=concept,
            namespace="http://fasb.org/us-gaap/2023",
            numeric_value=value,
            unit="USD",
            context_id=f"annual-{index}",
            period_type="duration",
            start_date="2022-10-01",
            end_date="2023-09-30",
            is_segment=False,
            dimensions={},
        )
        for index, value in enumerate((100.0, 101.0))
    ]

    results = service.reconcile_facts_for_filing(
        accession_number=accession,
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=ix_facts,
    )

    revenue = next(result for result in results if result.metric_id == "revenue")
    assert revenue.status == "ambiguous"
    assert revenue.ixbrl_value is None


def test_reconciliation_matches_exact_company_extension_concept():
    service = CrossSourceReconciliationService()
    accession = "0000320193-23-000106"
    concept = "ExampleCompanyRevenue"
    cf_fact = FactRecord(
        cik="0000320193",
        accession_number=accession,
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=100.0,
        normalized_value=100.0,
        unit="USD",
        taxonomy="custom",
        concept=concept,
        period_type="duration",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Reviewed custom concept mapping",
    )
    ix_fact = ParsedXBRLFact(
        accession_number=accession,
        concept_name=concept,
        namespace="http://example.com/2023",
        is_custom=True,
        numeric_value=100.0,
        unit="USD",
        context_id="annual-extension",
        period_type="duration",
        start_date="2022-10-01",
        end_date="2023-09-30",
        is_segment=False,
        dimensions={},
    )

    results = service.reconcile_facts_for_filing(
        accession_number=accession,
        cik="0000320193",
        company_facts=[cf_fact],
        ixbrl_facts=[ix_fact],
    )

    revenue = next(result for result in results if result.metric_id == "revenue")
    assert revenue.status == "exact_match"
    assert revenue.company_facts_concept == concept
    assert revenue.ixbrl_concept == concept


def test_segment_classification():
    classifier = SegmentClassifier()

    facts = [
        ParsedXBRLFact(
            accession_number="0000320193-23-000106",
            concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
            namespace="http://fasb.org/us-gaap/2023",
            numeric_value=200000000000.0,
            unit="USD",
            context_id="c_seg_iphone",
            period_type="duration",
            start_date="2022-10-01",
            end_date="2023-09-30",
            is_segment=True,
            dimensions={"ProductOrServiceAxis": "IPhoneMember"},
        ),
        ParsedXBRLFact(
            accession_number="0000320193-23-000106",
            concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
            namespace="http://fasb.org/us-gaap/2023",
            numeric_value=40000000000.0,
            unit="USD",
            context_id="c_seg_mac",
            period_type="duration",
            start_date="2022-10-01",
            end_date="2023-09-30",
            is_segment=True,
            dimensions={"ProductOrServiceAxis": "MacMember"},
        ),
        ParsedXBRLFact(
            accession_number="0000320193-23-000106",
            concept_name="Assets",
            namespace="http://fasb.org/us-gaap/2023",
            numeric_value=352583000000.0,
            unit="USD",
            context_id="c_entity",
            period_type="instant",
            start_date=None,
            end_date="2023-09-30",
            is_segment=False,
            dimensions={},
        ),
    ]

    report = classifier.classify_segments("0000320193-23-000106", facts)
    assert report.total_segment_facts == 2
    assert "ProductOrServiceAxis" in report.unique_axes
    assert "IPhoneMember" in report.unique_members
    assert "MacMember" in report.unique_members
    assert len(report.segments_by_axis["ProductOrServiceAxis"]) == 2


def test_reconciliation_persistence():
    repo = ReconciliationRepository()
    record = ReconciliationRecord(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        metric_id="revenue",
        canonical_name="Revenue",
        status="exact_match",
        company_facts_value=383285000000.0,
        ixbrl_value=383285000000.0,
        difference=0.0,
        company_facts_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        ixbrl_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        company_facts_unit="USD",
        ixbrl_unit="USD",
        company_facts_period="2023-09-30",
        ixbrl_period="2023-09-30",
        is_segment_mismatch=False,
        explanation="Exact match",
    )

    repo.delete_reconciliations_by_accession("0000320193-23-000106")
    repo.save_reconciliations([record])

    fetched = repo.get_reconciliations_by_accession("0000320193-23-000106")
    assert len(fetched) == 1
    assert fetched[0].metric_id == "revenue"
    assert fetched[0].status == "exact_match"
    assert fetched[0].difference == 0.0




def test_q4_vs_annual_reconciliation():
    """EXT-01: Verify that annual facts match annual facts, Q4 facts match Q4 facts,
    and annual facts are never matched against Q4 duration facts with identical end date."""
    service = CrossSourceReconciliationService()

    # 1. Annual CF Fact: 383,285,000,000 (~365 days, ended 2023-09-30)
    cf_annual_rev = FactRecord(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        metric_id="revenue",
        canonical_name="Revenue",
        raw_value=383285000000.0,
        normalized_value=383285000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_type="duration",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Selected annual fact",
    )

    # Q4 iXBRL Fact: 89,498,000,000 (~91 days, ended 2023-09-30)
    ix_q4_rev = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
        namespace="http://fasb.org/us-gaap/2023",
        numeric_value=89498000000.0,
        unit="USD",
        context_id="c_q4_2023",
        period_type="duration",
        start_date="2023-07-01",
        end_date="2023-09-30",
        is_segment=False,
    )

    # Annual iXBRL Fact: 383,285,000,000 (~365 days, ended 2023-09-30)
    ix_annual_rev = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
        namespace="http://fasb.org/us-gaap/2023",
        numeric_value=383285000000.0,
        unit="USD",
        context_id="c_annual_2023",
        period_type="duration",
        start_date="2022-10-01",
        end_date="2023-09-30",
        is_segment=False,
    )

    # Case A: Both Q4 and Annual exist in iXBRL -> Must prefer annual, NOT match Q4
    # Note: ix_q4_rev is intentionally first in list to test that selector doesn't blindly pick first item
    res_a = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_annual_rev],
        ixbrl_facts=[ix_q4_rev, ix_annual_rev],
    )
    rev_a = next(r for r in res_a if r.metric_id == "revenue")
    assert rev_a.status == "exact_match"
    assert rev_a.difference == 0.0
    assert rev_a.ixbrl_value == 383285000000.0

    # Case B: Only Q4 fact exists in iXBRL -> Must report period_mismatch, NOT false value_mismatch
    res_b = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_annual_rev],
        ixbrl_facts=[ix_q4_rev],
    )
    rev_b = next(r for r in res_b if r.metric_id == "revenue")
    assert rev_b.status == "period_mismatch"
    assert "quarterly" in rev_b.explanation.lower() or "duration" in rev_b.explanation.lower()

    # Case C: Genuine Annual value mismatch detected
    ix_annual_mismatch = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="RevenueFromContractWithCustomerExcludingAssessedTax",
        namespace="http://fasb.org/us-gaap/2023",
        numeric_value=380000000000.0,  # 3.285B diff
        unit="USD",
        context_id="c_annual_2023_err",
        period_type="duration",
        start_date="2022-10-01",
        end_date="2023-09-30",
        is_segment=False,
    )
    res_c = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_annual_rev],
        ixbrl_facts=[ix_annual_mismatch],
    )
    rev_c = next(r for r in res_c if r.metric_id == "revenue")
    assert rev_c.status == "value_mismatch"
    assert rev_c.difference == 3285000000.0

    # Case D: Instant balance sheet metric works unaffected
    cf_assets = FactRecord(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        metric_id="total_assets",
        canonical_name="Total Assets",
        raw_value=352583000000.0,
        normalized_value=352583000000.0,
        unit="USD",
        taxonomy="us-gaap",
        concept="Assets",
        period_type="instant",
        period_start=None,
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        form="10-K",
        status="selected",
        selection_explanation="Selected",
    )
    ix_assets = ParsedXBRLFact(
        accession_number="0000320193-23-000106",
        concept_name="Assets",
        namespace="http://fasb.org/us-gaap/2023",
        numeric_value=352583000000.0,
        unit="USD",
        context_id="c_instant_2023",
        period_type="instant",
        start_date=None,
        end_date="2023-09-30",
        is_segment=False,
    )
    res_d = service.reconcile_facts_for_filing(
        accession_number="0000320193-23-000106",
        cik="0000320193",
        company_facts=[cf_assets],
        ixbrl_facts=[ix_assets],
    )
    ast_d = next(r for r in res_d if r.metric_id == "total_assets")
    assert ast_d.status == "exact_match"



def test_complete_semantic_mapping_coverage():
    """SEM-01: Verify that all 10 canonical financial metrics have verified heuristic semantic coverage,
    period type compatibility, unit validation, rejection of false positives (e.g. gross margin % or
    investing cash flows), and safe ambiguous concept exposure."""
    mapper = SemanticMapper()

    canonical_10_expectations = [
        # (concept_name, period_type, unit, expected_metric_id)
        ("TotalRevenueAndOtherOperatingRevenue", "duration", "USD", "revenue"),
        ("ConsolidatedNetIncomeLossBeforeTax", "duration", "USD", "net_income"),
        ("GrossProfitLossFromOperations", "duration", "USD", "gross_profit"),
        ("OperatingProfitLossBeforeInterest", "duration", "USD", "operating_income"),
        ("TotalAssetsCarryingAmount", "instant", "USD", "total_assets"),
        ("TotalLiabilitiesNetOfCurrent", "instant", "USD", "total_liabilities"),
        ("CommonStockholdersEquityTotal", "instant", "USD", "stockholders_equity"),
        ("CashAndCashEquivalentsAtEndOfPeriod", "instant", "USD", "cash_and_cash_equivalents"),
        ("CashProvidedByUsedInOperatingActivitiesNet", "duration", "USD", "operating_cash_flow"),
        ("PaymentsToAcquirePropertyPlantAndEquipmentCapex", "duration", "USD", "capital_expenditure"),
    ]

    covered_metric_ids = set()
    for concept, ptype, unit, expected_id in canonical_10_expectations:
        res = mapper.evaluate_custom_concept(
            concept_name=concept,
            namespace="http://example.com/2026",
            period_type=ptype,
            unit=unit,
            is_segment=False,
        )
        assert res.is_mapped is True, f"Failed to map candidate concept '{concept}' to {expected_id}"
        assert res.candidate_metric_id == expected_id
        assert res.confidence_level == "candidate_for_review"
        assert res.namespace == "http://example.com/2026"
        covered_metric_ids.add(res.candidate_metric_id)

    # Ensure all 10 canonical metrics are represented
    assert len(covered_metric_ids) == 10

    # 1. Unit mismatch rejection (e.g. EUR instead of USD)
    res_unit = mapper.evaluate_custom_concept(
        concept_name="GrossProfitLossFromOperations",
        namespace="http://example.com/2026",
        period_type="duration",
        unit="EUR",
        is_segment=False,
    )
    assert res_unit.is_mapped is False
    assert res_unit.confidence_level == "unresolved"

    # 2. Instant vs duration mismatch rejection (e.g. Gross Profit with instant period)
    res_period = mapper.evaluate_custom_concept(
        concept_name="GrossProfitLossFromOperations",
        namespace="http://example.com/2026",
        period_type="instant",
        unit="USD",
        is_segment=False,
    )
    assert res_period.is_mapped is False

    # 3. Ambiguous concept matching multiple metrics
    # E.g. concept containing keywords matching multiple metrics
    res_ambig = mapper.evaluate_custom_concept(
        concept_name="TotalRevenueAndTotalOperatingIncome",
        namespace="http://example.com/2026",
        period_type="duration",
        unit="USD",
        is_segment=False,
    )
    assert res_ambig.is_mapped is False
    assert res_ambig.confidence_level == "unresolved"
    assert "ambiguous" in res_ambig.reason.lower()


def test_semantic_mapping_stockholders_equity():
    """SEM-01: Focused test for stockholders_equity alternative concepts and false positive guardrails."""
    mapper = SemanticMapper()

    # Valid candidates
    for name in ["TotalShareholdersEquity", "ShareholdersCapitalTotal", "CommonStockholdersEquity"]:
        res = mapper.evaluate_custom_concept(
            concept_name=name,
            namespace="http://example.com/2026",
            period_type="instant",
            unit="USD",
            is_segment=False,
        )
        assert res.is_mapped is True
        assert res.candidate_metric_id == "stockholders_equity"

    # Reject combined liabilities and equity
    res_comb = mapper.evaluate_custom_concept(
        concept_name="LiabilitiesAndStockholdersEquity",
        namespace="http://example.com/2026",
        period_type="instant",
        unit="USD",
        is_segment=False,
    )
    assert res_comb.is_mapped is False


def test_semantic_mapping_operating_cash_flow():
    """SEM-01: Focused test for operating_cash_flow concepts and rejection of investing/financing flows."""
    mapper = SemanticMapper()

    # Valid operating flows
    for name in ["CashProvidedByUsedInOperatingActivities", "NetCashFromOperatingActivities"]:
        res = mapper.evaluate_custom_concept(
            concept_name=name,
            namespace="http://example.com/2026",
            period_type="duration",
            unit="USD",
            is_segment=False,
        )
        assert res.is_mapped is True
        assert res.candidate_metric_id == "operating_cash_flow"

    # Reject cash flows from investing or financing activities
    for invalid in [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInFinancingActivities",
        "CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations",
    ]:
        res_inv = mapper.evaluate_custom_concept(
            concept_name=invalid,
            namespace="http://example.com/2026",
            period_type="duration",
            unit="USD",
            is_segment=False,
        )
        assert res_inv.is_mapped is False, f"Should have rejected non-operating cash flow concept: {invalid}"


def test_semantic_mapping_gross_profit():
    """SEM-01: Focused test for gross_profit concepts and rejection of margin percentages."""
    mapper = SemanticMapper()

    # Valid gross profit amount
    res = mapper.evaluate_custom_concept(
        concept_name="RevenueLessCostOfGoodsAndServicesSold",
        namespace="http://example.com/2026",
        period_type="duration",
        unit="USD",
        is_segment=False,
    )
    assert res.is_mapped is True
    assert res.candidate_metric_id == "gross_profit"

    # Reject gross margin percentage or ratio
    for rate_concept in ["GrossMarginPercentage", "GrossProfitMarginRatio", "GrossMarginPercent"]:
        res_rate = mapper.evaluate_custom_concept(
            concept_name=rate_concept,
            namespace="http://example.com/2026",
            period_type="duration",
            unit="USD",
            is_segment=False,
        )
        assert res_rate.is_mapped is False, f"Should have rejected gross margin rate concept: {rate_concept}"


def test_semantic_mapping_cash_and_cash_equivalents():
    """SEM-01: Focused test for cash_and_cash_equivalents and rejection of flow changes or restricted cash only."""
    mapper = SemanticMapper()

    # Valid cash and cash equivalents
    res = mapper.evaluate_custom_concept(
        concept_name="CashAndCashEquivalentsAtEndOfPeriod",
        namespace="http://example.com/2026",
        period_type="instant",
        unit="USD",
        is_segment=False,
    )
    assert res.is_mapped is True
    assert res.candidate_metric_id == "cash_and_cash_equivalents"

    # Reject duration cash flow changes (e.g. increase/decrease over period)
    res_change = mapper.evaluate_custom_concept(
        concept_name="CashAndCashEquivalentsPeriodIncreaseDecrease",
        namespace="http://example.com/2026",
        period_type="instant",
        unit="USD",
        is_segment=False,
    )
    assert res_change.is_mapped is False

    # Reject restricted cash only
    res_restr = mapper.evaluate_custom_concept(
        concept_name="RestrictedCashCurrent",
        namespace="http://example.com/2026",
        period_type="instant",
        unit="USD",
        is_segment=False,
    )
    assert res_restr.is_mapped is False
