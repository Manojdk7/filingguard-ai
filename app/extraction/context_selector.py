import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from app.extraction.taxonomy_mapping import MetricDefinition
from app.database.repositories.fact_repository import FactRecord

logger = logging.getLogger("filingguard.extraction.context_selector")


class ContextSelectionResult:
    def __init__(
        self,
        metric_id: str,
        canonical_name: str,
        status: str,  # 'selected', 'ambiguous', 'missing'
        selected_fact: Optional[FactRecord] = None,
        all_candidates: Optional[List[FactRecord]] = None,
        explanation: str = ""
    ):
        self.metric_id = metric_id
        self.canonical_name = canonical_name
        self.status = status
        self.selected_fact = selected_fact
        self.all_candidates = all_candidates or []
        self.explanation = explanation


class FactContextSelector:
    """
    Evaluates candidate facts from SEC Company Facts for a given metric and target filing.
    Enforces rules:
    - Accession number matching
    - Form matching (10-K)
    - Period matching (annual FY context, matching the filing's report period date within 52/53-week tolerance)
    - Period type matching (duration for Income/Cash Flow, instant for Balance Sheet)
    - Unit validation (USD vs non-currency or differing scales)
    - Ambiguity exposure over guessing
    """

    def __init__(self, date_tolerance_days: int = 7):
        self.date_tolerance_days = date_tolerance_days

    def calculate_date_difference_days(self, date_a: Optional[str], date_b: Optional[str]) -> Optional[int]:
        """Calculates absolute days between two YYYY-MM-DD date strings."""
        if not date_a or not date_b:
            return None
        try:
            da = datetime.strptime(date_a[:10], "%Y-%m-%d").date()
            db = datetime.strptime(date_b[:10], "%Y-%m-%d").date()
            return abs((da - db).days)
        except Exception:
            return None

    def calculate_duration_days(self, start_date: str, end_date: str) -> Optional[int]:
        """Calculates days between two YYYY-MM-DD date strings."""
        try:
            d_start = datetime.strptime(start_date[:10], "%Y-%m-%d")
            d_end = datetime.strptime(end_date[:10], "%Y-%m-%d")
            return (d_end - d_start).days
        except Exception:
            return None

    def select_fact_for_metric(
        self,
        cik: str,
        target_accession: str,
        target_fiscal_year: Optional[int],
        metric_def: MetricDefinition,
        raw_facts_data: Dict[str, Any],
        target_report_period: Optional[str] = None,
        date_tolerance_days: Optional[int] = None,
    ) -> ContextSelectionResult:
        """
        Inspects all candidate taxonomy concepts for metric_def,
        evaluates candidate facts against accession, form, fiscal year, report period, unit, and period type,
        and returns a ContextSelectionResult.
        """
        tolerance = date_tolerance_days if date_tolerance_days is not None else self.date_tolerance_days
        us_gaap_facts = raw_facts_data.get("facts", {}).get("us-gaap", {})
        all_records: List[FactRecord] = []
        eligible_candidates: List[FactRecord] = []

        # Step 1: Iterate candidate concepts in priority order
        for concept in metric_def.concepts:
            concept_data = us_gaap_facts.get(concept)
            if not concept_data:
                continue

            units_dict = concept_data.get("units", {})
            for unit_name, facts_list in units_dict.items():
                for raw_fact in facts_list:
                    # Parse raw fields
                    f_accn = raw_fact.get("accn")
                    f_form = raw_fact.get("form")
                    f_fy = raw_fact.get("fy")
                    f_fp = raw_fact.get("fp")
                    f_start = raw_fact.get("start")
                    f_end = raw_fact.get("end")
                    f_val = raw_fact.get("val")
                    f_filed = raw_fact.get("filed")
                    f_frame = raw_fact.get("frame")

                    if f_val is None:
                        continue

                    # Filter only facts tied to this specific filing accession
                    if f_accn != target_accession:
                        continue

                    # Evaluate candidate eligibility
                    reasons: List[str] = []
                    is_eligible = True

                    # 1. Form check
                    if f_form != "10-K":
                        is_eligible = False
                        reasons.append(f"Form '{f_form}' is not annual 10-K")

                    # 2. Fiscal year / Report Period check
                    # A 10-K presents 2-3 years of comparative financial data under fy=target_fy.
                    # We match target_report_period against f_end.
                    # Under 52/53-week fiscal year calendars, the actual fiscal year end may differ
                    # by up to 7 calendar days from the cover report date.
                    if target_report_period and f_end:
                        diff_days = self.calculate_date_difference_days(f_end, target_report_period)
                        if diff_days is None:
                            is_eligible = False
                            reasons.append(f"Invalid date format: f_end={f_end}, target={target_report_period}")
                        elif diff_days > tolerance:
                            is_eligible = False
                            reasons.append(
                                f"Period end {f_end} differs from filing report date {target_report_period} by {diff_days} days (exceeds tolerance of {tolerance} days)"
                            )
                        elif diff_days > 0:
                            reasons.append(
                                f"Accepted via 52/53-week tolerance ({diff_days}d delta from report date {target_report_period})"
                            )
                    elif target_fiscal_year is not None and f_fy is not None:
                        # Fallback if target_report_period not supplied
                        if f_end and not f_end.startswith(str(target_fiscal_year)):
                            try:
                                d_end = datetime.strptime(f_end[:10], "%Y-%m-%d").date()
                                if abs(d_end.year - target_fiscal_year) > 1:
                                    is_eligible = False
                                    reasons.append(f"Period end {f_end} does not match target fiscal year {target_fiscal_year}")
                            except Exception:
                                is_eligible = False
                                reasons.append(f"Period end {f_end} does not match target fiscal year {target_fiscal_year}")

                    # 3. Unit validation
                    if unit_name != metric_def.default_unit:
                        is_eligible = False
                        reasons.append(f"Unit '{unit_name}' does not match required '{metric_def.default_unit}'")

                    # 4. Period type & duration / instant validation
                    if metric_def.period_type == "duration":
                        if f_start is None:
                            is_eligible = False
                            reasons.append("Missing start date for duration metric")
                        else:
                            duration_days = self.calculate_duration_days(f_start, f_end)
                            # Annual reporting period should span ~330 - 380 days
                            if duration_days is None or duration_days < 330:
                                is_eligible = False
                                reasons.append(f"Duration {duration_days} days is quarterly/partial, not full annual FY")

                        # Fiscal period flag check
                        if f_fp != "FY" and f_fp is not None:
                            is_eligible = False
                            reasons.append(f"Fiscal period '{f_fp}' indicates interim/quarterly fact, not FY")

                    elif metric_def.period_type == "instant":
                        # Instant facts must not have duration start date
                        if f_start is not None and f_start != f_end:
                            is_eligible = False
                            reasons.append("Instant balance sheet metric has duration start date")

                    # Build candidate record
                    status = "candidate" if is_eligible else "rejected"
                    explanation = "; ".join(reasons) if reasons else "Eligible annual candidate fact"

                    record = FactRecord(
                        cik=cik,
                        accession_number=target_accession,
                        metric_id=metric_def.metric_id,
                        canonical_name=metric_def.canonical_name,
                        raw_value=float(f_val),
                        normalized_value=float(f_val),
                        unit=unit_name,
                        taxonomy="us-gaap",
                        concept=concept,
                        period_type=metric_def.period_type,
                        period_start=f_start,
                        period_end=f_end,
                        fiscal_year=int(f_fy) if f_fy is not None else 0,
                        fiscal_period=f_fp or "FY",
                        form=f_form or "10-K",
                        filed_date=f_filed,
                        frame=f_frame,
                        status=status,
                        selection_explanation=explanation,
                    )
                    all_records.append(record)

                    if is_eligible:
                        eligible_candidates.append(record)

        # Step 2: Determine selection outcome
        if not eligible_candidates:
            explanation = f"No eligible facts matched accession {target_accession} and criteria for {metric_def.canonical_name}"
            return ContextSelectionResult(
                metric_id=metric_def.metric_id,
                canonical_name=metric_def.canonical_name,
                status="missing",
                selected_fact=None,
                all_candidates=all_records,
                explanation=explanation,
            )

        # If multiple eligible candidates exist:
        # Prefer the closest matching date when multiple candidates exist (e.g. exact match over tolerance match)
        if target_report_period and len(eligible_candidates) > 1:
            def _get_diff(c: FactRecord) -> int:
                d = self.calculate_date_difference_days(c.period_end, target_report_period)
                return 999 if d is None else d

            diffs = [_get_diff(c) for c in eligible_candidates]
            min_diff = min(diffs)
            closest_candidates = [c for c in eligible_candidates if _get_diff(c) == min_diff]
            if closest_candidates and len(closest_candidates) < len(eligible_candidates):
                eligible_candidates = closest_candidates

        # If exactly 1 eligible candidate exists
        if len(eligible_candidates) == 1:
            selected = eligible_candidates[0]
            selected.status = "selected"
            selected_delta = self.calculate_date_difference_days(selected.period_end, target_report_period) if target_report_period else 0
            if selected_delta and selected_delta > 0:
                selected.selection_explanation = (
                    f"Selected primary fact for {metric_def.canonical_name} using concept {selected.concept} ({selected.unit}) "
                    f"[accepted via 52/53-week calendar tolerance: {selected_delta}d delta from report date {target_report_period}]"
                )
                logger.info(
                    f"Selected fact for {metric_def.canonical_name} using 52/53-week tolerance "
                    f"({selected_delta}d delta: {selected.period_end} vs report date {target_report_period})"
                )
            else:
                selected.selection_explanation = f"Selected primary fact for {metric_def.canonical_name} using concept {selected.concept} ({selected.unit})"
            return ContextSelectionResult(
                metric_id=metric_def.metric_id,
                canonical_name=metric_def.canonical_name,
                status="selected",
                selected_fact=selected,
                all_candidates=all_records,
                explanation=selected.selection_explanation,
            )

        # If multiple eligible candidates exist:
        # Check if they share the exact same value
        unique_values = {c.raw_value for c in eligible_candidates}
        if len(unique_values) == 1:
            # Deterministically choose candidate with highest concept priority in metric_def
            concept_priority = {c: idx for idx, c in enumerate(metric_def.concepts)}
            eligible_candidates.sort(key=lambda x: concept_priority.get(x.concept, 999))
            selected = eligible_candidates[0]
            selected.status = "selected"
            selected_delta = self.calculate_date_difference_days(selected.period_end, target_report_period) if target_report_period else 0
            if selected_delta and selected_delta > 0:
                selected.selection_explanation = (
                    f"Resolved synonymous candidates with identical values using primary concept {selected.concept} "
                    f"[accepted via 52/53-week calendar tolerance: {selected_delta}d delta from report date {target_report_period}]"
                )
                logger.info(
                    f"Resolved fact for {metric_def.canonical_name} using 52/53-week tolerance "
                    f"({selected_delta}d delta: {selected.period_end} vs report date {target_report_period})"
                )
            else:
                selected.selection_explanation = f"Resolved synonymous candidates with identical values using primary concept {selected.concept}"
            return ContextSelectionResult(
                metric_id=metric_def.metric_id,
                canonical_name=metric_def.canonical_name,
                status="selected",
                selected_fact=selected,
                all_candidates=all_records,
                explanation=selected.selection_explanation,
            )

        # Multiple candidates with conflicting values: mark as ambiguous, do not guess
        for c in eligible_candidates:
            c.status = "ambiguous"
            c.selection_explanation = f"Ambiguous candidate conflict with distinct values: {unique_values}"

        return ContextSelectionResult(
            metric_id=metric_def.metric_id,
            canonical_name=metric_def.canonical_name,
            status="ambiguous",
            selected_fact=None,
            all_candidates=all_records,
            explanation=f"Exposed ambiguous candidates ({len(eligible_candidates)}) with divergent reported values: {unique_values}",
        )
