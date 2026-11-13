import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.database.repositories.fact_repository import FactRecord, FactRepository
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.database.repositories.validation_repository import ValidationRecord, ValidationRepository
from app.database.repositories.xbrl_fact_repository import XBRLFactRepository
from app.validation.accounting_equation import validate_accounting_equation
from app.validation.cross_statement import validate_cross_statement_metric
from app.validation.operating_income import validate_operating_income
from app.validation.segment_reconciliation import SegmentReconciliationService
from app.validation.yoy_analysis import validate_yoy_variance

logger = logging.getLogger("filingguard.validation.engine")

# -----------------------------------------------------------------------
# Operating expense component concept names for aggregation (VAL-01)
# -----------------------------------------------------------------------
_OPEX_CONSOLIDATED_CONCEPTS = frozenset({
    "operatingexpenses",
    "costsandexpenses",
    "operatingcostsdecoratingexpense",
})

_OPEX_COMPONENT_CONCEPTS = {
    "ResearchAndDevelopmentExpense": "researchanddevelopmentexpense",
    "SellingGeneralAndAdministrativeExpense": "sellinggeneralandadministrativeexpense",
    "SellingAndMarketingExpense": "sellingandmarketingexpense",
    "GeneralAndAdministrativeExpense": "generalandadministrativeexpense",
    "TechnologyAndContentExpense": "technologyandcontentexpense",
    "FulfillmentExpense": "fulfillmentexpense",
    "MarketingExpense": "marketingexpense",
    "OtherOperatingExpenses": "otheroperatingexpenses",
    "OtherOperatingIncomeExpenseNet": "otheroperatingincomeexpensenet",
    "DepreciationAndAmortization": "depreciationandamortization",
    "CostOfRevenue": "costofrevenue",
    "CostOfGoodsAndServicesSold": "costofgoodsandservicessold",
}

# When SG&A is present, do NOT also add its subcomponents to avoid double-counting
_SGA_SUBCOMPONENTS = frozenset({
    "sellingandmarketingexpense",
    "generalandadministrativeexpense",
    "marketingexpense",
})

# Concepts that must NOT be included in opex aggregation (they are non-operating or tax)
_OPEX_EXCLUSIONS = frozenset({
    "incometaxexpensebenefit",
    "interestexpense",
    "interestincomeexpensenet",
    "othernonoperatingincomeexpense",
    "investmentincomeinterest",
})


class FinancialValidationEngine:
    """Deterministic coordinator executing financial statement validation rules."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        fact_repo: Optional[FactRepository] = None,
        filing_repo: Optional[FilingRepository] = None,
        xbrl_repo: Optional[XBRLFactRepository] = None,
        scoring_repo: Optional[ScoringRepository] = None,
        validation_repo: Optional[ValidationRepository] = None,
    ):
        self.config_path = config_path or (settings.CONFIG_DIR / "validation_rules.json")
        self.config = self._load_config()

        self.fact_repo = fact_repo or FactRepository()
        self.filing_repo = filing_repo or FilingRepository()
        self.xbrl_repo = xbrl_repo or XBRLFactRepository()
        self.scoring_repo = scoring_repo or ScoringRepository()
        self.validation_repo = validation_repo or ValidationRepository()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load validation config from {self.config_path}: {e}")
        return {
            "version": "1.0.0",
            "rules": {
                "balance_sheet_equation": {"enabled": True, "relative_tolerance": 0.005, "absolute_tolerance": 1000000.0},
                "operating_income_presentation": {"enabled": True, "relative_tolerance": 0.001, "absolute_tolerance": 100000.0},
                "yoy_variance": {"enabled": True, "warning_threshold_pct": 40.0},
                "cross_statement_net_income": {"enabled": True, "absolute_tolerance": 1.0},
                "cross_statement_cash": {"enabled": True, "absolute_tolerance": 1.0},
                "segment_reconciliation": {"enabled": True, "tolerance_pct": 0.01},
            },
        }

    @staticmethod
    def _aggregate_operating_expenses(
        xbrl_facts: list,
        period_end: str,
    ) -> Tuple[Optional[float], Optional[dict], Optional[dict]]:
        """Attempt to find or aggregate operating expenses from iXBRL facts.

        Strategy:
        1. Prefer a single consolidated OperatingExpenses or CostsAndExpenses fact.
        2. If none, aggregate compatible non-overlapping component facts.

        Returns:
            (total_opex, component_breakdown, evidence_refs) or (None, None, None) if unavailable.
        """
        # --- Step 1: Look for consolidated total ---
        for xf in xbrl_facts:
            if (
                xf.concept_name.lower() in _OPEX_CONSOLIDATED_CONCEPTS
                and xf.period_type == "duration"
                and not xf.is_segment
                and xf.end_date == period_end
                and xf.numeric_value is not None
            ):
                return (
                    xf.numeric_value,
                    {"consolidated": xf.numeric_value},
                    {
                        "source": "consolidated",
                        "concept": xf.concept_name,
                        "locator": xf.source_locator,
                    },
                )

        # --- Step 2: Component aggregation ---
        # Collect candidate component facts matching the period
        candidates: Dict[str, Any] = {}  # lowercase concept -> xf
        for xf in xbrl_facts:
            cn_lower = xf.concept_name.lower()
            if (
                cn_lower in _OPEX_EXCLUSIONS
                or xf.period_type != "duration"
                or xf.is_segment
                or xf.end_date != period_end
                or xf.numeric_value is None
            ):
                continue
            # Check if this is a known component
            for display_name, norm_name in _OPEX_COMPONENT_CONCEPTS.items():
                if cn_lower == norm_name and norm_name not in candidates:
                    candidates[norm_name] = xf
                    break

        if not candidates:
            return (None, None, None)

        # Prevent double-counting: if SG&A is present, remove its sub-components
        has_sga = "sellinggeneralandadministrativeexpense" in candidates
        if has_sga:
            for sub in _SGA_SUBCOMPONENTS:
                candidates.pop(sub, None)

        # Prevent double-counting: if CostOfRevenue is present, don't also use CostOfGoodsAndServicesSold
        if "costofrevenue" in candidates and "costofgoodsandservicessold" in candidates:
            candidates.pop("costofgoodsandservicessold", None)

        # We need at least 2 components to consider this a valid aggregation
        if len(candidates) < 2:
            return (None, None, None)

        total = 0.0
        component_breakdown: Dict[str, float] = {}
        evidence: Dict[str, Any] = {"source": "component_aggregation", "components": []}
        for norm_name, xf in candidates.items():
            total += xf.numeric_value
            component_breakdown[xf.concept_name] = xf.numeric_value
            evidence["components"].append(xf.concept_name)

        return (total, component_breakdown, evidence)

    def _find_prior_year_fact(
        self,
        current_fact: FactRecord,
        all_facts: List[FactRecord],
    ) -> Optional[FactRecord]:
        """Identify prior-year comparative fact for the same metric within the filing."""
        candidates = [
            f for f in all_facts
            if f.metric_id == current_fact.metric_id
            and f.id != current_fact.id
            and f.period_end != current_fact.period_end
        ]
        if not candidates:
            return None

        # Sort candidates by period_end descending to pick the immediate prior fiscal year
        try:
            curr_end = datetime.strptime(current_fact.period_end, "%Y-%m-%d")
            candidates_with_dates = []
            for c in candidates:
                try:
                    c_end = datetime.strptime(c.period_end, "%Y-%m-%d")
                    # Must be before current end, approximately 300-420 days prior
                    diff_days = (curr_end - c_end).days
                    if 300 <= diff_days <= 420:
                        candidates_with_dates.append((diff_days, c))
                except Exception:
                    continue

            if candidates_with_dates:
                # Pick closest to 365 days
                candidates_with_dates.sort(key=lambda x: abs(x[0] - 365))
                return candidates_with_dates[0][1]
        except Exception:
            pass

        return None

    def validate_filing(
        self,
        accession_number: str,
        fact_overrides: Optional[Dict[str, float]] = None,
        persist: bool = True,
    ) -> List[ValidationRecord]:
        """Execute all enabled financial validation rules for an accession and persist results.
        
        Optional fact_overrides allows re-running validations against reviewer-corrected values.
        """
        filing = self.filing_repo.get_by_accession(accession_number)
        cik = filing.cik if filing else "0000000000"

        # Fetch facts
        selected_facts = self.fact_repo.get_selected_facts_by_accession(accession_number)
        all_facts = self.fact_repo.get_all_facts_by_accession(accession_number)
        facts_by_metric = {f.metric_id: f for f in selected_facts}

        def _val(m_id: str) -> Optional[float]:
            if fact_overrides and m_id in fact_overrides:
                return fact_overrides[m_id]
            f = facts_by_metric.get(m_id)
            return f.raw_value if f else None

        # Fetch confidence scores from Phase 6
        confidence_records = self.scoring_repo.get_metric_scores_by_accession(accession_number)
        conf_by_metric = {c.metric_id: c for c in confidence_records}

        # Fetch parsed iXBRL facts for secondary statement disclosures (e.g. OperatingExpenses)
        xbrl_facts = self.xbrl_repo.get_facts_by_accession(accession_number)

        rules_cfg = self.config.get("rules", {})
        results: List[ValidationRecord] = []

        # -------------------------------------------------------------
        # 1. Rule A: Accounting Equation (Assets = Liabilities + Equity)
        # -------------------------------------------------------------
        eq_cfg = rules_cfg.get("balance_sheet_equation", {})
        if eq_cfg.get("enabled", True):
            assets_fact = facts_by_metric.get("total_assets")
            liab_fact = facts_by_metric.get("total_liabilities")
            eq_fact = facts_by_metric.get("stockholders_equity")

            res_eq = validate_accounting_equation(
                accession_number=accession_number,
                cik=cik,
                reported_assets=_val("total_assets"),
                reported_liabilities=_val("total_liabilities"),
                reported_equity=_val("stockholders_equity"),
                relative_tolerance=eq_cfg.get("relative_tolerance", 0.005),
                absolute_tolerance=eq_cfg.get("absolute_tolerance", 1000000.0),
                confidence_scores=conf_by_metric,
                evidence_refs={
                    "total_assets_concept": assets_fact.concept if assets_fact else None,
                    "total_liabilities_concept": liab_fact.concept if liab_fact else None,
                    "stockholders_equity_concept": eq_fact.concept if eq_fact else None,
                },
            )
            results.append(res_eq)

        # -------------------------------------------------------------
        # 2. Rule B: Operating Income Presentation (Gross Profit - Opex)
        # -------------------------------------------------------------
        op_cfg = rules_cfg.get("operating_income_presentation", {})
        if op_cfg.get("enabled", True):
            op_inc_fact = facts_by_metric.get("operating_income")
            gp_fact = facts_by_metric.get("gross_profit")

            # Traceable Operating Expenses from iXBRL parsed facts (not invented)
            # VAL-01: Use aggregation helper that prefers consolidated, falls back to components
            opex_value = None
            opex_evidence: Dict[str, Any] = {}
            component_breakdown: Optional[Dict[str, float]] = None

            if op_inc_fact and xbrl_facts:
                opex_total, comp_breakdown, opex_ev = self._aggregate_operating_expenses(
                    xbrl_facts, op_inc_fact.period_end,
                )
                if opex_total is not None:
                    opex_value = opex_total
                    component_breakdown = comp_breakdown
                    opex_evidence = opex_ev or {}

            res_op = validate_operating_income(
                accession_number=accession_number,
                cik=cik,
                reported_operating_income=_val("operating_income"),
                reported_gross_profit=_val("gross_profit"),
                reported_operating_expenses=opex_value,
                relative_tolerance=op_cfg.get("relative_tolerance", 0.001),
                absolute_tolerance=op_cfg.get("absolute_tolerance", 100000.0),
                confidence_scores=conf_by_metric,
                evidence_refs={
                    "operating_income_concept": op_inc_fact.concept if op_inc_fact else None,
                    "gross_profit_concept": gp_fact.concept if gp_fact else None,
                    "operating_expenses_source": opex_evidence.get("source"),
                    "operating_expenses_components": opex_evidence.get("components"),
                    "operating_expenses_concept": opex_evidence.get("concept"),
                },
                component_breakdown=component_breakdown,
            )
            results.append(res_op)

        # -------------------------------------------------------------
        # 3. Rule C: Year-over-Year (YoY) Variance Analysis
        # -------------------------------------------------------------
        yoy_cfg = rules_cfg.get("yoy_variance", {})
        if yoy_cfg.get("enabled", True):
            warn_threshold = yoy_cfg.get("warning_threshold_pct", 40.0)

            for m_id, curr_fact in facts_by_metric.items():
                prior_fact = self._find_prior_year_fact(curr_fact, all_facts)
                curr_val = _val(m_id)

                res_yoy = validate_yoy_variance(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m_id,
                    canonical_name=curr_fact.canonical_name,
                    current_value=curr_val,
                    prior_value=prior_fact.raw_value if prior_fact else None,
                    warning_threshold_pct=warn_threshold,
                    current_period=curr_fact.period_end,
                    prior_period=prior_fact.period_end if prior_fact else None,
                    current_unit=curr_fact.unit,
                    prior_unit=prior_fact.unit if prior_fact else curr_fact.unit,
                    confidence_scores=conf_by_metric,
                    evidence_refs={
                        "current_fact_id": curr_fact.id,
                        "prior_fact_id": prior_fact.id if prior_fact else None,
                    },
                )
                results.append(res_yoy)

        # -------------------------------------------------------------
        # 4. Rule D: Cross-Statement Consistency (Net Income & Cash)
        # -------------------------------------------------------------
        cs_ni_cfg = rules_cfg.get("cross_statement_net_income", {})
        if cs_ni_cfg.get("enabled", True):
            ni_fact = facts_by_metric.get("net_income")
            # VAL-02: Look for Net Income in iXBRL facts from the Cash Flow Statement.
            # We must ensure we find an INDEPENDENT fact from a different statement
            # (Cash Flow Statement) rather than re-using the same Income Statement fact.
            cf_ni_value = None
            cf_ni_fact_id = None
            is_same_fact = False

            if ni_fact and xbrl_facts:
                # Find Cash Flow Statement anchor facts to identify Cash Flow statement cluster
                cf_anchor_ids = [
                    xf.id for xf in xbrl_facts
                    if xf.id is not None and xf.concept_name in (
                        "NetCashProvidedByUsedInOperatingActivities",
                        "DepreciationDepletionAndAmortization",
                        "ShareBasedCompensation",
                    )
                ]

                # Collect all NetIncomeLoss / ProfitLoss duration facts
                ni_xbrl_candidates = [
                    xf for xf in xbrl_facts
                    if xf.concept_name.lower() in ("netincomeloss", "profitloss")
                    and xf.period_type == "duration"
                    and not xf.is_segment
                    and xf.end_date == ni_fact.period_end
                    and xf.numeric_value is not None
                ]

                if len(ni_xbrl_candidates) >= 2:
                    # Look for candidate nearest to cash flow statement anchors
                    cf_candidate = None
                    if cf_anchor_ids:
                        min_dist = float("inf")
                        for cand in ni_xbrl_candidates:
                            if cand.id is not None:
                                dist = min(abs(cand.id - aid) for aid in cf_anchor_ids)
                                if dist < min_dist and dist <= 30:  # within 30 facts of cash flow line items
                                    min_dist = dist
                                    cf_candidate = cand

                    if cf_candidate is not None:
                        cf_ni_value = cf_candidate.numeric_value
                        cf_ni_fact_id = cf_candidate.id
                        is_same_fact = False
                    else:
                        # Multiple candidates exist but none in cash flow section, or all identical
                        cf_ni_value = ni_xbrl_candidates[0].numeric_value
                        is_same_fact = True
                elif len(ni_xbrl_candidates) == 1:
                    # Only one instance found in filing — cannot verify cross-statement independence
                    cf_ni_value = ni_xbrl_candidates[0].numeric_value
                    is_same_fact = True

            res_cs_ni = validate_cross_statement_metric(
                accession_number=accession_number,
                cik=cik,
                rule_id="cross_statement_net_income",
                rule_name="Net Income Cross-Statement Consistency",
                source_statement="Income Statement",
                target_statement="Cash Flow Statement Reconciliation",
                source_value=_val("net_income"),
                target_value=cf_ni_value,
                tolerance=cs_ni_cfg.get("absolute_tolerance", 1.0),
                source_period=ni_fact.period_end if ni_fact else None,
                target_period=ni_fact.period_end if ni_fact else None,
                evidence_refs={"concept": ni_fact.concept if ni_fact else None},
                is_same_fact=is_same_fact,
            )
            results.append(res_cs_ni)

        cs_cash_cfg = rules_cfg.get("cross_statement_cash", {})
        if cs_cash_cfg.get("enabled", True):
            cash_fact = facts_by_metric.get("cash_and_cash_equivalents")
            # Look for Cash and Cash Equivalents in iXBRL ending cash
            cf_cash_value = None
            if cash_fact and xbrl_facts:
                for xf in xbrl_facts:
                    if (
                        "cashandcashequivalents" in xf.concept_name.lower()
                        and xf.period_type == "instant"
                        and not xf.is_segment
                        and xf.end_date == cash_fact.period_end
                        and xf.numeric_value is not None
                    ):
                        cf_cash_value = xf.numeric_value
                        break

            res_cs_cash = validate_cross_statement_metric(
                accession_number=accession_number,
                cik=cik,
                rule_id="cross_statement_cash",
                rule_name="Cash & Cash Equivalents Cross-Statement Consistency",
                source_statement="Balance Sheet",
                target_statement="Cash Flow Statement Ending Cash",
                source_value=_val("cash_and_cash_equivalents"),
                target_value=cf_cash_value,
                tolerance=cs_cash_cfg.get("absolute_tolerance", 1.0),
                source_period=cash_fact.period_end if cash_fact else None,
                target_period=cash_fact.period_end if cash_fact else None,
                evidence_refs={"concept": cash_fact.concept if cash_fact else None},
            )
            results.append(res_cs_cash)

        # -------------------------------------------------------------
        # 5. Rule E: Segment Reconciliation (Dimensional vs Consolidated)
        # -------------------------------------------------------------
        seg_cfg = rules_cfg.get("segment_reconciliation", {})
        if seg_cfg.get("enabled", True):
            rev_fact = facts_by_metric.get("revenue")
            consolidated_rev = _val("revenue")
            if rev_fact and xbrl_facts and consolidated_rev is not None:
                seg_facts = [
                    xf for xf in xbrl_facts
                    if xf.is_segment
                    and xf.period_type == "duration"
                    and xf.end_date == rev_fact.period_end
                    and xf.numeric_value is not None
                    and xf.numeric_value > 0
                    and "revenue" in xf.concept_name.lower()
                ]
                seen_contexts = set()
                unique_seg_facts = []
                for sf in seg_facts:
                    if sf.context_id not in seen_contexts:
                        seen_contexts.add(sf.context_id)
                        unique_seg_facts.append(sf)

                if len(unique_seg_facts) >= 2:
                    seg_vals = [sf.numeric_value for sf in unique_seg_facts]
                    rollup = SegmentReconciliationService.verify_segment_sum(
                        metric_id="revenue",
                        consolidated_value=consolidated_rev,
                        segment_values=seg_vals,
                        tolerance_pct=seg_cfg.get("tolerance_pct", 0.01),
                    )
                    status_seg = "PASS" if rollup.is_valid else "WARNING"
                    expl = (
                        f"Segment revenue breakdown reconciles with consolidated revenue: "
                        f"{rollup.segment_count} segments sum to ${rollup.segment_sum:,.2f} vs consolidated ${rollup.consolidated_value:,.2f} "
                        f"(diff: ${rollup.difference:,.2f} within tolerance ${rollup.tolerance:,.2f})."
                        if rollup.is_valid
                        else f"Segment revenue breakdown discrepancy: {rollup.segment_count} segments sum to ${rollup.segment_sum:,.2f} "
                        f"differing from consolidated ${rollup.consolidated_value:,.2f} by ${rollup.difference:,.2f} (exceeds tolerance ${rollup.tolerance:,.2f})."
                    )
                    results.append(
                        ValidationRecord(
                            accession_number=accession_number,
                            cik=cik,
                            rule_id="segment_reconciliation",
                            rule_name="Segment Breakdown Reconciliation (Revenue)",
                            rule_version="1.0.0",
                            validation_category="segment_reconciliation",
                            status=status_seg,
                            expected_value=rollup.consolidated_value,
                            actual_value=rollup.segment_sum,
                            absolute_difference=rollup.difference,
                            relative_difference=rollup.difference / abs(rollup.consolidated_value) if rollup.consolidated_value else 0.0,
                            configured_tolerance=rollup.tolerance,
                            input_metrics={"consolidated_revenue": rollup.consolidated_value, "segment_count": rollup.segment_count},
                            evidence_references={"segment_concepts": [sf.concept_name for sf in unique_seg_facts[:5]]},
                            explanation=expl,
                            failure_reason=None if rollup.is_valid else f"Segment revenue mismatch: diff ${rollup.difference:,.2f}",
                            recommendation="Segment breakdowns verified against consolidated revenue." if rollup.is_valid else "Review segment axis allocations and inter-segment eliminations.",
                        )
                    )
                else:
                    results.append(
                        ValidationRecord(
                            accession_number=accession_number,
                            cik=cik,
                            rule_id="segment_reconciliation",
                            rule_name="Segment Breakdown Reconciliation",
                            rule_version="1.0.0",
                            validation_category="segment_reconciliation",
                            status="NOT_EVALUATED",
                            expected_value=consolidated_rev,
                            actual_value=None,
                            configured_tolerance=0.0,
                            input_metrics={"consolidated_revenue": consolidated_rev},
                            evidence_references={},
                            explanation="Segment reconciliation skipped: no dimensional segment breakdowns found in filing facts for revenue.",
                            failure_reason="No dimensional segment facts disclosed",
                            recommendation="Confirm whether the issuer discloses revenue by operating/geographic segment.",
                        )
                    )
            else:
                results.append(
                    ValidationRecord(
                        accession_number=accession_number,
                        cik=cik,
                        rule_id="segment_reconciliation",
                        rule_name="Segment Breakdown Reconciliation",
                        rule_version="1.0.0",
                        validation_category="segment_reconciliation",
                        status="NOT_EVALUATED",
                        expected_value=None,
                        actual_value=None,
                        configured_tolerance=0.0,
                        input_metrics={},
                        evidence_references={},
                        explanation="Segment reconciliation skipped: consolidated revenue not available.",
                        failure_reason="Missing consolidated revenue metric",
                        recommendation="Ensure consolidated revenue is extracted before segment validation.",
                    )
                )

        # Persist results idempotently if requested
        if persist:
            self.validation_repo.save_validations(results)
        logger.info(f"Validated accession {accession_number}: generated {len(results)} validation records (persist={persist}).")
        return results

