import logging
import re
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.extraction.taxonomy_mapping import TaxonomyMappingManager, MetricDefinition
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact
from app.database.repositories.reconciliation_repository import CustomConceptCandidateRecord

logger = logging.getLogger("filingguard.extraction.semantic_mapping")


class CustomConceptMappingResult(BaseModel):
    custom_concept: str
    namespace: str
    is_mapped: bool
    candidate_metric_id: Optional[str] = None
    candidate_metric_name: Optional[str] = None
    confidence_level: str  # 'candidate_for_review', 'unresolved'
    reason: str


class SemanticMapper:
    """
    Evaluates company-specific custom XBRL concepts against canonical metrics.
    Enforces rules:
    - Preserves custom concept names and namespaces unchanged.
    - Never forces an uncertain mapping into canonical metrics.
    - Submits potential mappings only as candidates for review.
    - Distinguishes non-additive/disclosure tags from financial metrics.
    """

    def __init__(self, taxonomy_manager: Optional[TaxonomyMappingManager] = None):
        self.taxonomy_manager = taxonomy_manager or TaxonomyMappingManager()

    def evaluate_custom_concept(
        self,
        concept_name: str,
        namespace: str,
        period_type: str,
        unit: Optional[str],
        is_segment: bool,
        label: Optional[str] = None,
    ) -> CustomConceptMappingResult:
        """
        Analyzes a custom concept using conservative deterministic heuristics across all 10 canonical metrics.
        Flags candidate matches for human review or marks them as unresolved.
        """
        # If the concept is dimensioned/segment-level, it must never be mapped to a consolidated metric
        if is_segment:
            return CustomConceptMappingResult(
                custom_concept=concept_name,
                namespace=namespace,
                is_mapped=False,
                candidate_metric_id=None,
                candidate_metric_name=None,
                confidence_level="unresolved",
                reason=f"Custom concept '{concept_name}' is dimensioned/segment-level and cannot represent a consolidated metric.",
            )

        name_lower = concept_name.lower()
        search_text = f"{name_lower} {label.lower()}" if label else name_lower

        # Heuristic rules for canonical metric candidates
        candidates = []
        for metric in self.taxonomy_manager.get_all_metrics():
            # Check period type compatibility
            if metric.period_type != period_type:
                continue

            # Check unit compatibility (financial metrics generally require currency USD)
            if metric.default_unit == "USD" and unit and unit != "USD":
                continue

            # Check concept keyword affinity across all 10 canonical metrics
            if metric.metric_id == "revenue":
                if any(k in search_text for k in ["revenue", "sales"]) and not any(ex in search_text for ex in ["deferredrevenue", "unearnedrevenue", "costofgoods"]):
                    candidates.append((metric, "Contains revenue/sales keywords with compatible duration and currency"))

            elif metric.metric_id == "net_income":
                is_net = any(k in search_text for k in ["netincome", "netloss", "profitloss"])
                if is_net and "comprehensive" not in search_text and "gross" not in search_text and "operating" not in search_text:
                    candidates.append((metric, "Contains net income/loss keywords with compatible duration and currency"))

            elif metric.metric_id == "operating_income":
                if any(k in search_text for k in ["operatingincome", "operatingloss", "operatingprofit"]) and "nonoperating" not in search_text:
                    candidates.append((metric, "Contains operating income keywords with compatible duration and currency"))

            elif metric.metric_id == "gross_profit":
                # Ensure percentage/margin ratio is never mapped to monetary gross profit
                is_rate = any(r in search_text for r in ["percent", "percentage", "marginpercent", "marginratio", "margin_ratio", "marginrate", "margin_rate", "%"])
                if not is_rate and any(k in search_text for k in ["grossprofit", "grossmargin", "revenuelesscostofgoods", "revenuelesscostofrevenue", "gross profit"]):
                    candidates.append((metric, "Contains gross profit keywords with compatible duration and currency"))

            elif metric.metric_id == "total_assets":
                if any(k in search_text for k in ["totalassets", "total assets"]) or ("asset" in search_text and "total" in search_text):
                    candidates.append((metric, "Contains total assets keywords with compatible instant and currency"))

            elif metric.metric_id == "total_liabilities":
                # Must not confuse with combined liabilities and equity
                if ("liabilit" in search_text and "total" in search_text) and not any(ex in search_text for ex in ["andequity", "andstockholders", "andshareholders"]):
                    candidates.append((metric, "Contains total liabilities keywords with compatible instant and currency"))

            elif metric.metric_id == "stockholders_equity":
                # Must not confuse combined liabilities and equity with equity alone
                is_combined = any(cb in search_text for cb in ["liabilitiesand", "liabilities and", "andliabilities"])
                if not is_combined and any(k in search_text for k in [
                    "stockholdersequity", "shareholdersequity", "totalequity",
                    "shareholderscapital", "commonstockholdersequity", "stockholders' equity",
                    "shareholders' equity", "total shareholders' equity", "total equity"
                ]):
                    candidates.append((metric, "Contains stockholders/shareholders equity keywords with compatible instant and currency"))

            elif metric.metric_id == "cash_and_cash_equivalents":
                # Must avoid mapping restricted-only cash or period duration cash changes
                is_flow_change = any(fc in search_text for fc in ["periodincreasedecrease", "increase decrease", "effectofexchange", "net change"])
                is_restricted_only = ("restrictedcash" in search_text or "restricted cash" in search_text) and not ("andcashequivalents" in search_text or "and cash" in search_text)
                if not is_flow_change and not is_restricted_only and any(k in search_text for k in [
                    "cashandcashequivalents", "cashcashequivalents", "cash and cash equivalents",
                    "cashequivalents", "cash at end of period"
                ]):
                    candidates.append((metric, "Contains cash and cash equivalents keywords with compatible instant and currency"))

            elif metric.metric_id == "operating_cash_flow":
                # Strictly reject cash flows from investing or financing activities
                is_non_operating = any(no in search_text for no in ["investing", "financing", "discontinuedoperations", "discontinued operations"])
                if not is_non_operating and any(k in search_text for k in [
                    "netcashprovidedbyusedinoperatingactivities", "cashprovidedbyusedinoperatingactivities",
                    "cashflowsfromoperatingactivities", "cash flows from operating activities",
                    "net cash provided by operating activities", "operatingcashflow", "operating cash flow",
                    "netcashfromoperatingactivities", "cashfromoperatingactivities", "cash from operating activities"
                ]):
                    candidates.append((metric, "Contains operating cash flow keywords with compatible duration and currency"))

            elif metric.metric_id == "capital_expenditure":
                # Strictly avoid cash inflows / proceeds from asset sales
                if not any(pr in search_text for pr in ["proceeds", "saleof", "sale of"]) and any(k in search_text for k in [
                    "capex", "capitalexpenditure", "capital expenditure",
                    "paymentstoacquirepropertyplant", "paymentstoacquireproductiveassets",
                    "purchaseofpropertyplant"
                ]):
                    candidates.append((metric, "Contains capital expenditure keywords with compatible duration and currency"))

        if len(candidates) == 1:
            m_def, reason = candidates[0]
            return CustomConceptMappingResult(
                custom_concept=concept_name,
                namespace=namespace,
                is_mapped=True,
                candidate_metric_id=m_def.metric_id,
                candidate_metric_name=m_def.canonical_name,
                confidence_level="candidate_for_review",
                reason=f"Candidate proposal: {reason}. Subject to human verification.",
            )
        elif len(candidates) > 1:
            return CustomConceptMappingResult(
                custom_concept=concept_name,
                namespace=namespace,
                is_mapped=False,
                candidate_metric_id=None,
                candidate_metric_name=None,
                confidence_level="unresolved",
                reason=f"Ambiguous candidate: concept matches multiple potential metrics: {[c[0].canonical_name for c in candidates]}.",
            )

        return CustomConceptMappingResult(
            custom_concept=concept_name,
            namespace=namespace,
            is_mapped=False,
            candidate_metric_id=None,
            candidate_metric_name=None,
            confidence_level="unresolved",
            reason=f"Custom extension '{concept_name}' does not match standard canonical criteria.",
        )

    def extract_custom_candidates_from_facts(
        self,
        accession_number: str,
        parsed_facts: List[ParsedXBRLFact],
    ) -> List[CustomConceptCandidateRecord]:
        """Scans parsed XBRL facts for custom concepts and generates candidate review records."""
        unique_custom = {}
        for f in parsed_facts:
            if f.is_custom and f.concept_name not in unique_custom:
                unique_custom[f.concept_name] = f

        records: List[CustomConceptCandidateRecord] = []
        for concept_name, f in unique_custom.items():
            eval_res = self.evaluate_custom_concept(
                concept_name=concept_name,
                namespace=f.namespace,
                period_type=f.period_type,
                unit=f.unit,
                is_segment=f.is_segment,
            )
            records.append(CustomConceptCandidateRecord(
                accession_number=accession_number,
                custom_concept=concept_name,
                namespace=f.namespace,
                candidate_metric_id=eval_res.candidate_metric_id,
                candidate_metric_name=eval_res.candidate_metric_name,
                confidence_level=eval_res.confidence_level,
                reason=eval_res.reason,
                is_reviewed=False,
            ))
        return records

