import pytest
from app.extraction.taxonomy_mapping import TaxonomyMappingManager, MetricDefinition
from app.extraction.context_selector import FactContextSelector
from app.sec.company_facts import CompanyFactsClient, MalformedCompanyFactsError
from app.sec.client import SECClient
from app.database.repositories.fact_repository import FactRepository, FactRecord


def test_taxonomy_mapping_loading():
    manager = TaxonomyMappingManager()
    metrics = manager.get_all_metrics()
    assert len(metrics) >= 10
    metric_ids = [m.metric_id for m in metrics]
    expected = [
        "revenue", "net_income", "gross_profit", "operating_income",
        "total_assets", "total_liabilities", "stockholders_equity",
        "cash_and_cash_equivalents", "operating_cash_flow", "capital_expenditure"
    ]
    for exp in expected:
        assert exp in metric_ids


def test_company_facts_malformed_structure():
    client = CompanyFactsClient()
    with pytest.raises(MalformedCompanyFactsError):
        # Missing 'facts' dictionary
        client.client = type("MockClient", (), {"get_json": lambda *args, **kwargs: {"cik": 320193}})()
        client.fetch_company_facts("320193")


def test_annual_vs_quarterly_fact_selection():
    selector = FactContextSelector()
    m_def = MetricDefinition(
        metric_id="revenue",
        canonical_name="Revenue",
        statement="income_statement",
        period_type="duration",
        default_unit="USD",
        concepts=["RevenueFromContractWithCustomerExcludingAssessedTax"],
        description="Test revenue"
    )

    mock_raw_facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            # Quarterly fact (duration ~90 days)
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "Q4",
                                "start": "2023-07-01",
                                "end": "2023-09-30",
                                "val": 89498000000,
                            },
                            # Annual FY fact (duration 365 days)
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 383285000000,
                            }
                        ]
                    }
                }
            }
        }
    }

    result = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-23-000106",
        target_fiscal_year=2023,
        metric_def=m_def,
        raw_facts_data=mock_raw_facts,
    )

    assert result.status == "selected"
    assert result.selected_fact is not None
    # Must select the annual fact (383285000000), never the quarterly fact (89498000000)
    assert result.selected_fact.raw_value == 383285000000
    assert result.selected_fact.fiscal_period == "FY"


def test_instant_vs_duration_separation():
    selector = FactContextSelector()
    # Balance sheet instant metric
    m_def = MetricDefinition(
        metric_id="total_assets",
        canonical_name="Total Assets",
        statement="balance_sheet",
        period_type="instant",
        default_unit="USD",
        concepts=["Assets"],
        description="Test assets"
    )

    mock_raw_facts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            # Invalid duration-tagged asset fact
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 999999,
                            },
                            # Valid instant asset fact (no start date)
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "start": None,
                                "end": "2023-09-30",
                                "val": 352583000000,
                            }
                        ]
                    }
                }
            }
        }
    }

    result = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-23-000106",
        target_fiscal_year=2023,
        metric_def=m_def,
        raw_facts_data=mock_raw_facts,
    )

    assert result.status == "selected"
    assert result.selected_fact is not None
    assert result.selected_fact.raw_value == 352583000000
    assert result.selected_fact.period_start is None


def test_unit_validation_rejection():
    selector = FactContextSelector()
    m_def = MetricDefinition(
        metric_id="revenue",
        canonical_name="Revenue",
        statement="income_statement",
        period_type="duration",
        default_unit="USD",
        concepts=["Revenues"],
        description="Test revenue"
    )

    # Unit is EUR instead of USD
    mock_raw_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "EUR": [
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 1000000,
                            }
                        ]
                    }
                }
            }
        }
    }

    result = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-23-000106",
        target_fiscal_year=2023,
        metric_def=m_def,
        raw_facts_data=mock_raw_facts,
    )

    # Rejected because unit doesn't match USD; metric remains missing
    assert result.status == "missing"
    assert result.selected_fact is None


def test_duplicate_candidates_ambiguity_exposure():
    selector = FactContextSelector()
    m_def = MetricDefinition(
        metric_id="operating_income",
        canonical_name="Operating Income",
        statement="income_statement",
        period_type="duration",
        default_unit="USD",
        concepts=["OperatingIncomeLoss", "OtherOperatingIncome"],
        description="Test operating income"
    )

    # Two conflicting values reported for the same accession and period
    mock_raw_facts = {
        "facts": {
            "us-gaap": {
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 114301000000,
                            }
                        ]
                    }
                },
                "OtherOperatingIncome": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000320193-23-000106",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 120000000000,  # Conflicting value
                            }
                        ]
                    }
                }
            }
        }
    }

    result = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-23-000106",
        target_fiscal_year=2023,
        metric_def=m_def,
        raw_facts_data=mock_raw_facts,
    )

    assert result.status == "ambiguous"
    assert result.selected_fact is None
    assert "conflicting" in result.explanation.lower() or "divergent" in result.explanation.lower()


def test_missing_metric_not_fabricated():
    selector = FactContextSelector()
    m_def = MetricDefinition(
        metric_id="capital_expenditure",
        canonical_name="Capital Expenditure",
        statement="cash_flow",
        period_type="duration",
        default_unit="USD",
        concepts=["PaymentsToAcquirePropertyPlantAndEquipment"],
        description="Test capex"
    )

    # Empty facts dictionary
    mock_raw_facts = {"facts": {"us-gaap": {}}}

    result = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-23-000106",
        target_fiscal_year=2023,
        metric_def=m_def,
        raw_facts_data=mock_raw_facts,
    )

    assert result.status == "missing"
    assert result.selected_fact is None


def test_fact_repository_persistence():
    repo = FactRepository()
    record = FactRecord(
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
        filed_date="2023-11-03",
        frame="CY2023",
        status="selected",
        selection_explanation="Test selection",
    )

    repo.delete_facts_by_accession("0000320193-23-000106")
    repo.save_facts([record])

    selected = repo.get_selected_facts_by_accession("0000320193-23-000106")
    assert len(selected) == 1
    assert selected[0].metric_id == "revenue"
    assert selected[0].raw_value == 383285000000.0
    assert selected[0].unit == "USD"




def test_52_53_week_date_window():
    """EXT-03: Verify that 52/53-week fiscal year end dates within configurable tolerance
    (up to 7 days) are accepted, closer dates are preferred, prior-year comparative facts
    and wrong quarterly contexts are strictly rejected, and instant vs duration metrics
    are handled correctly."""
    selector = FactContextSelector(date_tolerance_days=7)

    m_def_rev = MetricDefinition(
        metric_id="revenue",
        canonical_name="Revenue",
        statement="income_statement",
        period_type="duration",
        default_unit="USD",
        concepts=["RevenueFromContractWithCustomerExcludingAssessedTax"],
        description="Revenue test"
    )

    # 1. Exact report-date match (0 days delta)
    raw_exact = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": "2025-10-01",
                            "end": "2026-09-30",
                            "val": 400000000000,
                        }]
                    }
                }
            }
        }
    }
    res_exact = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_exact,
        target_report_period="2026-09-30",
    )
    assert res_exact.status == "selected"
    assert res_exact.selected_fact.raw_value == 400000000000
    assert "52/53-week" not in res_exact.selected_fact.selection_explanation

    # 2. 1-day difference (accepted)
    raw_1d = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": "2025-09-30",
                            "end": "2026-09-29",  # 1 day before 2026-09-30
                            "val": 401000000000,
                        }]
                    }
                }
            }
        }
    }
    res_1d = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_1d,
        target_report_period="2026-09-30",
    )
    assert res_1d.status == "selected"
    assert res_1d.selected_fact.raw_value == 401000000000
    assert "52/53-week" in res_1d.selected_fact.selection_explanation

    # 3. 4-day difference (spec scenario: e.g. 2026-09-26 vs 2026-09-30)
    raw_4d = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": "2025-09-27",
                            "end": "2026-09-26",  # 4 days before 2026-09-30, duration=364 days
                            "val": 404000000000,
                        }]
                    }
                }
            }
        }
    }
    res_4d = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_4d,
        target_report_period="2026-09-30",
    )
    assert res_4d.status == "selected"
    assert res_4d.selected_fact.raw_value == 404000000000
    assert "4d delta" in res_4d.selected_fact.selection_explanation

    # 4. 7-day difference (boundary of tolerance: accepted)
    raw_7d = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": "2025-09-24",
                            "end": "2026-09-23",  # 7 days before 2026-09-30, duration=364 days
                            "val": 407000000000,
                        }]
                    }
                }
            }
        }
    }
    res_7d = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_7d,
        target_report_period="2026-09-30",
    )
    assert res_7d.status == "selected"
    assert res_7d.selected_fact.raw_value == 407000000000

    # 5. More than 7 days difference (8 days: rejected)
    raw_8d = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": "2025-09-23",
                            "end": "2026-09-22",  # 8 days before 2026-09-30
                            "val": 408000000000,
                        }]
                    }
                }
            }
        }
    }
    res_8d = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_8d,
        target_report_period="2026-09-30",
    )
    assert res_8d.status == "missing"
    assert res_8d.selected_fact is None

    # 6. Prior-year comparative period rejection (~365 days away)
    raw_prior = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": "2024-10-01",
                            "end": "2025-09-30",  # Prior year comparative fact
                            "val": 350000000000,
                        }]
                    }
                }
            }
        }
    }
    res_prior = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_prior,
        target_report_period="2026-09-30",
    )
    assert res_prior.status == "missing"
    assert res_prior.selected_fact is None

    # 7. Wrong quarterly context rejection (e.g. Q4 with end date within tolerance)
    raw_q4_near = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "Q4",  # Quarterly flag
                            "start": "2026-07-01",
                            "end": "2026-09-28",  # 2 days delta, but duration is ~89 days
                            "val": 95000000000,
                        }]
                    }
                }
            }
        }
    }
    res_q4 = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_q4_near,
        target_report_period="2026-09-30",
    )
    assert res_q4.status == "missing"
    assert res_q4.selected_fact is None

    # 8. Preference for closest matching date when multiple candidates exist
    raw_multi = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "accn": "0000320193-26-000001",
                                "form": "10-K",
                                "fy": 2026,
                                "fp": "FY",
                                "start": "2025-09-27",
                                "end": "2026-09-26",  # 4 days delta
                                "val": 404000000000,
                            },
                            {
                                "accn": "0000320193-26-000001",
                                "form": "10-K",
                                "fy": 2026,
                                "fp": "FY",
                                "start": "2025-10-01",
                                "end": "2026-09-30",  # 0 days delta (exact)
                                "val": 400000000000,
                            },
                        ]
                    }
                }
            }
        }
    }
    res_multi = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_rev,
        raw_facts_data=raw_multi,
        target_report_period="2026-09-30",
    )
    assert res_multi.status == "selected"
    # Exact match (0 days delta) must be preferred over 4 days delta
    assert res_multi.selected_fact.raw_value == 400000000000
    assert res_multi.selected_fact.period_end == "2026-09-30"

    # 9. Correct instant vs duration handling
    m_def_assets = MetricDefinition(
        metric_id="total_assets",
        canonical_name="Total Assets",
        statement="balance_sheet",
        period_type="instant",
        default_unit="USD",
        concepts=["Assets"],
        description="Assets test"
    )
    raw_assets = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [{
                            "accn": "0000320193-26-000001",
                            "form": "10-K",
                            "fy": 2026,
                            "fp": "FY",
                            "start": None,
                            "end": "2026-09-26",  # 4 days delta, instant fact
                            "val": 360000000000,
                        }]
                    }
                }
            }
        }
    }
    res_assets = selector.select_fact_for_metric(
        cik="0000320193",
        target_accession="0000320193-26-000001",
        target_fiscal_year=2026,
        metric_def=m_def_assets,
        raw_facts_data=raw_assets,
        target_report_period="2026-09-30",
    )
    assert res_assets.status == "selected"
    assert res_assets.selected_fact.raw_value == 360000000000
    assert res_assets.selected_fact.period_start is None
    assert "4d delta" in res_assets.selected_fact.selection_explanation
