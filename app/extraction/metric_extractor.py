import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.sec.client import SECClient, normalize_cik
from app.sec.company_facts import CompanyFactsClient
from app.sec.submissions import SubmissionsManager
from app.database.repositories.filing_repository import FilingRepository, FilingRecord
from app.database.repositories.fact_repository import FactRepository, FactRecord
from app.extraction.taxonomy_mapping import TaxonomyMappingManager, MetricDefinition
from app.extraction.context_selector import FactContextSelector, ContextSelectionResult

logger = logging.getLogger("filingguard.extraction.metric_extractor")


class MetricExtractionSummary(BaseModel):
    metric_id: str
    canonical_name: str
    status: str  # 'selected', 'ambiguous', 'missing'
    selected_value: Optional[float] = None
    unit: Optional[str] = None
    fiscal_period: Optional[str] = None
    fiscal_year: Optional[int] = None
    concept: Optional[str] = None
    accession_number: str
    candidate_count: int
    selection_explanation: str


class FilingExtractionReport(BaseModel):
    cik: str
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    accession_number: str
    filing_date: str
    report_period: Optional[str] = None
    target_fiscal_year: Optional[int] = None
    metrics: List[MetricExtractionSummary]
    selected_metrics_count: int
    ambiguous_metrics_count: int
    missing_metrics_count: int


class MetricExtractor:
    """
    Coordinates SEC Company Facts extraction, concept matching,
    context selection, and persistence.
    """

    def __init__(
        self,
        company_facts_client: Optional[CompanyFactsClient] = None,
        submissions_manager: Optional[SubmissionsManager] = None,
        taxonomy_manager: Optional[TaxonomyMappingManager] = None,
        context_selector: Optional[FactContextSelector] = None,
        filing_repo: Optional[FilingRepository] = None,
        fact_repo: Optional[FactRepository] = None,
    ):
        self.company_facts_client = company_facts_client or CompanyFactsClient()
        self.submissions_manager = submissions_manager or SubmissionsManager()
        self.taxonomy_manager = taxonomy_manager or TaxonomyMappingManager()
        self.context_selector = context_selector or FactContextSelector()
        self.filing_repo = filing_repo or FilingRepository()
        self.fact_repo = fact_repo or FactRepository()

    def extract_metrics_for_filing(
        self,
        cik: str,
        accession_number: Optional[str] = None,
        use_cache: bool = True,
        persist: bool = True,
    ) -> FilingExtractionReport:
        """
        Extracts all canonical financial metrics from Company Facts for the specified filing.
        If accession_number is None, retrieves or uses the latest 10-K filing.
        """
        norm_cik = normalize_cik(cik)

        # 1. Retrieve or locate filing record
        filing: Optional[FilingRecord] = None
        if accession_number:
            filing = self.filing_repo.get_by_accession(accession_number)

        if not filing:
            filing = self.submissions_manager.retrieve_and_persist_latest_10k(norm_cik)

        target_accn = filing.accession_number
        target_fy: Optional[int] = None
        if filing.report_period:
            try:
                target_fy = int(filing.report_period.split("-")[0])
            except Exception:
                target_fy = None

        # 2. Retrieve company facts JSON
        facts_data = self.company_facts_client.fetch_company_facts(norm_cik, use_cache=use_cache)
        company_name = facts_data.get("entityName") or filing.company_name

        # 3. Clear previously persisted facts for this accession if re-extracting
        if persist:
            self.fact_repo.delete_facts_by_accession(target_accn)

        # 4. Extract metrics defined in canonical taxonomy mapping
        metric_defs = self.taxonomy_manager.get_all_metrics()
        all_fact_records: List[FactRecord] = []
        metric_summaries: List[MetricExtractionSummary] = []

        selected_count = 0
        ambiguous_count = 0
        missing_count = 0

        for m_def in metric_defs:
            result = self.context_selector.select_fact_for_metric(
                cik=norm_cik,
                target_accession=target_accn,
                target_fiscal_year=target_fy,
                metric_def=m_def,
                raw_facts_data=facts_data,
                target_report_period=filing.report_period,
            )

            all_fact_records.extend(result.all_candidates)

            summary = MetricExtractionSummary(
                metric_id=m_def.metric_id,
                canonical_name=m_def.canonical_name,
                status=result.status,
                selected_value=result.selected_fact.raw_value if result.selected_fact else None,
                unit=result.selected_fact.unit if result.selected_fact else None,
                fiscal_period=result.selected_fact.fiscal_period if result.selected_fact else None,
                fiscal_year=result.selected_fact.fiscal_year if result.selected_fact else None,
                concept=result.selected_fact.concept if result.selected_fact else None,
                accession_number=target_accn,
                candidate_count=len(result.all_candidates),
                selection_explanation=result.explanation,
            )
            metric_summaries.append(summary)

            if result.status == "selected":
                selected_count += 1
            elif result.status == "ambiguous":
                ambiguous_count += 1
            else:
                missing_count += 1

        # 5. Persist facts if requested
        if persist:
            self.fact_repo.save_facts(all_fact_records)

        return FilingExtractionReport(
            cik=norm_cik,
            company_name=company_name,
            ticker=filing.ticker,
            accession_number=target_accn,
            filing_date=filing.filing_date,
            report_period=filing.report_period,
            target_fiscal_year=target_fy,
            metrics=metric_summaries,
            selected_metrics_count=selected_count,
            ambiguous_metrics_count=ambiguous_count,
            missing_metrics_count=missing_count,
        )
