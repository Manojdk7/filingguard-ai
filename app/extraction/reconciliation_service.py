import datetime
import logging
from typing import Dict, List, Optional, Tuple
from app.database.repositories.fact_repository import FactRecord
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact
from app.database.repositories.reconciliation_repository import ReconciliationRecord
from app.extraction.taxonomy_mapping import TaxonomyMappingManager, MetricDefinition

logger = logging.getLogger("filingguard.extraction.reconciliation_service")


def _calc_duration_days(start_str: Optional[str], end_str: Optional[str]) -> Optional[int]:
    """Calculate duration in days between two YYYY-MM-DD date strings."""
    if not start_str or not end_str:
        return None
    try:
        s = datetime.datetime.strptime(start_str[:10], "%Y-%m-%d").date()
        e = datetime.datetime.strptime(end_str[:10], "%Y-%m-%d").date()
        return (e - s).days
    except Exception:
        return None


class CrossSourceReconciliationService:
    """
    Reconciles Path A (SEC Company Facts) with Path B (Original Inline XBRL facts).
    Strictly verifies compatibility of period, duration/instant context, units,
    and consolidation scope before comparing values.
    """

    def __init__(self, taxonomy_manager: Optional[TaxonomyMappingManager] = None):
        self.taxonomy_manager = taxonomy_manager or TaxonomyMappingManager()

    def reconcile_facts_for_filing(
        self,
        accession_number: str,
        cik: str,
        company_facts: List[FactRecord],
        ixbrl_facts: List[ParsedXBRLFact],
    ) -> List[ReconciliationRecord]:
        """
        Reconciles facts between Company Facts and Inline XBRL across all canonical metrics.
        """
        metrics = self.taxonomy_manager.get_all_metrics()
        records: List[ReconciliationRecord] = []

        # Index Company Facts by metric_id (only selected primary facts)
        cf_by_metric: Dict[str, FactRecord] = {
            f.metric_id: f for f in company_facts if f.status == "selected"
        }

        # Index Inline XBRL facts by concept_name
        # Keep entity-wide and segment facts accessible
        ixbrl_entity_by_concept: Dict[str, List[ParsedXBRLFact]] = {}
        ixbrl_segment_by_concept: Dict[str, List[ParsedXBRLFact]] = {}

        for f in ixbrl_facts:
            if f.is_segment or f.dimensions:
                ixbrl_segment_by_concept.setdefault(f.concept_name, []).append(f)
            else:
                ixbrl_entity_by_concept.setdefault(f.concept_name, []).append(f)

        for m in metrics:
            cf_fact = cf_by_metric.get(m.metric_id)

            # Include the selected Company Facts concept so exact company-extension
            # concepts can be reconciled without guessing a similar standard tag.
            concepts = set(m.concepts)
            if cf_fact:
                concepts.add(cf_fact.concept)

            # Find matching entity-wide iXBRL facts for canonical or exact concepts.
            matching_ixbrl: List[ParsedXBRLFact] = []
            for c in concepts:
                if c in ixbrl_entity_by_concept:
                    matching_ixbrl.extend(ixbrl_entity_by_concept[c])

            # Case 1: Missing in both sources
            if not cf_fact and not matching_ixbrl:
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="missing_in_both",
                    explanation=f"Metric '{m.canonical_name}' is not reported in Company Facts or Inline XBRL for accession {accession_number}.",
                ))
                continue

            # Case 2: Missing in Inline XBRL but present in Company Facts
            if cf_fact and not matching_ixbrl:
                # Check if segment-only facts exist in iXBRL
                has_segments = any(c in ixbrl_segment_by_concept for c in m.concepts)
                if has_segments:
                    records.append(ReconciliationRecord(
                        accession_number=accession_number,
                        cik=cik,
                        metric_id=m.metric_id,
                        canonical_name=m.canonical_name,
                        status="segment_vs_consolidated_mismatch",
                        company_facts_value=cf_fact.raw_value,
                        company_facts_concept=cf_fact.concept,
                        company_facts_unit=cf_fact.unit,
                        company_facts_period=cf_fact.period_end,
                        is_segment_mismatch=True,
                        explanation="Metric exists as a consolidated fact in Company Facts but only as dimensional segment facts in Inline XBRL.",
                    ))
                else:
                    records.append(ReconciliationRecord(
                        accession_number=accession_number,
                        cik=cik,
                        metric_id=m.metric_id,
                        canonical_name=m.canonical_name,
                        status="missing_in_ixbrl",
                        company_facts_value=cf_fact.raw_value,
                        company_facts_concept=cf_fact.concept,
                        company_facts_unit=cf_fact.unit,
                        company_facts_period=cf_fact.period_end,
                        explanation=f"Metric '{m.canonical_name}' present in Company Facts but missing in Inline XBRL.",
                    ))
                continue

            # Case 3: Missing in Company Facts but present in Inline XBRL
            if not cf_fact and matching_ixbrl:
                # Pick the most compatible candidate from iXBRL
                ix = matching_ixbrl[0]
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="missing_in_company_facts",
                    ixbrl_value=ix.numeric_value,
                    ixbrl_concept=ix.concept_name,
                    ixbrl_unit=ix.unit,
                    ixbrl_period=ix.end_date,
                    explanation=f"Metric '{m.canonical_name}' present in Inline XBRL ({ix.concept_name}) but missing in SEC Company Facts.",
                ))
                continue

            # Case 4: Present in both sources -> Perform cross-source compatibility and value check
            cf_is_duration = (cf_fact.period_type == "duration")
            cf_duration = _calc_duration_days(cf_fact.period_start, cf_fact.period_end)
            cf_is_annual = (cf_fact.fiscal_period == "FY") or (cf_duration is not None and 330 <= cf_duration <= 380)

            # Filter candidates that match period_type and end_date
            compatible_candidates: List[Tuple[ParsedXBRLFact, Optional[int]]] = []
            for ix in matching_ixbrl:
                if ix.period_type != cf_fact.period_type:
                    continue
                if ix.end_date != cf_fact.period_end:
                    continue

                if cf_is_duration:
                    ix_dur = _calc_duration_days(ix.start_date, ix.end_date)
                    if ix_dur is None:
                        continue
                    if cf_duration is not None and abs(ix_dur - cf_duration) > 7:
                        continue
                    if cf_is_annual:
                        # Allow normal and 53-week fiscal years, but not quarter-length periods.
                        if ix_dur < 330 or ix_dur > 380:
                            continue
                    compatible_candidates.append((ix, ix_dur))
                else:
                    # Instant balance sheet metrics (no duration check needed)
                    compatible_candidates.append((ix, None))

            if not compatible_candidates:
                # No compatible fact found (e.g. quarterly fact cannot match annual fact, or end dates differ)
                unknown_duration_candidates = [
                    candidate
                    for candidate in matching_ixbrl
                    if cf_is_duration
                    and candidate.period_type == cf_fact.period_type
                    and candidate.end_date == cf_fact.period_end
                    and _calc_duration_days(candidate.start_date, candidate.end_date) is None
                ]
                ix_alt = unknown_duration_candidates[0] if unknown_duration_candidates else matching_ixbrl[0]
                ix_alt_dur = _calc_duration_days(ix_alt.start_date, ix_alt.end_date)
                same_end_duration_without_start = (
                    cf_is_duration
                    and ix_alt.period_type == cf_fact.period_type
                    and ix_alt.end_date == cf_fact.period_end
                    and ix_alt_dur is None
                )
                if same_end_duration_without_start:
                    status = "not_evaluated"
                    expl = (
                        "Period compatibility could not be evaluated because the Inline XBRL "
                        "duration is missing its start date."
                    )
                elif cf_is_duration and cf_is_annual and ix_alt_dur is not None and ix_alt_dur < 300:
                    status = "period_mismatch"
                    expl = (
                        f"Duration mismatch: Company Facts reports annual period ({cf_duration or '~365'} days, ended {cf_fact.period_end}) "
                        f"vs Inline XBRL reporting quarterly/partial duration ({ix_alt_dur} days, ended {ix_alt.end_date}). "
                        f"Quarterly fact cannot be reconciled against annual fact."
                    )
                else:
                    status = "period_mismatch"
                    expl = (
                        f"Period mismatch: Company Facts ended {cf_fact.period_end} ({cf_fact.period_type}) "
                        f"vs Inline XBRL ended {ix_alt.end_date} ({ix_alt.period_type})."
                    )

                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status=status,
                    company_facts_value=cf_fact.raw_value,
                    ixbrl_value=ix_alt.numeric_value,
                    difference=None,
                    company_facts_concept=cf_fact.concept,
                    ixbrl_concept=ix_alt.concept_name,
                    company_facts_unit=cf_fact.unit,
                    ixbrl_unit=ix_alt.unit,
                    company_facts_period=cf_fact.period_end,
                    ixbrl_period=ix_alt.end_date,
                    explanation=expl,
                ))
                continue

            # Rank candidates: prefer closest duration, concept match, and unit match
            def _candidate_rank(item: Tuple[ParsedXBRLFact, Optional[int]]):
                cand_ix, cand_dur = item
                dur_diff = (
                    abs(cand_dur - (cf_duration or 365))
                    if (cand_dur is not None and cf_is_duration)
                    else 0
                )
                concept_match = 0 if cand_ix.concept_name == cf_fact.concept else 1
                unit_match = 0 if cand_ix.unit == cf_fact.unit else 1
                return (unit_match, dur_diff, concept_match)

            compatible_candidates.sort(key=_candidate_rank)
            best_rank = _candidate_rank(compatible_candidates[0])
            equally_ranked = [
                candidate
                for candidate in compatible_candidates
                if _candidate_rank(candidate) == best_rank
            ]
            candidate_values = {
                fact.numeric_value
                for fact, _ in equally_ranked
                if fact.numeric_value is not None
            }
            if len(candidate_values) > 1:
                chosen_ix = next(fact for fact, _ in equally_ranked if fact.numeric_value is not None)
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="ambiguous",
                    company_facts_value=cf_fact.raw_value,
                    ixbrl_value=None,
                    company_facts_concept=cf_fact.concept,
                    ixbrl_concept=chosen_ix.concept_name,
                    company_facts_unit=cf_fact.unit,
                    ixbrl_unit=chosen_ix.unit,
                    company_facts_period=cf_fact.period_end,
                    ixbrl_period=chosen_ix.end_date,
                    explanation=(
                        "Multiple equally compatible entity-wide Inline XBRL facts "
                        "have different values; no candidate was selected."
                    ),
                ))
                continue

            chosen_ix, _ = next(
                (
                    (fact, duration)
                    for fact, duration in equally_ranked
                    if fact.numeric_value is not None
                ),
                equally_ranked[0],
            )

            # Check unit compatibility
            if cf_fact.unit != chosen_ix.unit:
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="unit_mismatch",
                    company_facts_value=cf_fact.raw_value,
                    ixbrl_value=chosen_ix.numeric_value,
                    difference=abs(cf_fact.raw_value - (chosen_ix.numeric_value or 0)),
                    company_facts_concept=cf_fact.concept,
                    ixbrl_concept=chosen_ix.concept_name,
                    company_facts_unit=cf_fact.unit,
                    ixbrl_unit=chosen_ix.unit,
                    company_facts_period=cf_fact.period_end,
                    ixbrl_period=chosen_ix.end_date,
                    explanation=f"Unit mismatch: Company Facts uses '{cf_fact.unit}' vs Inline XBRL uses '{chosen_ix.unit}'.",
                ))
                continue

            # Compare values
            val_cf = cf_fact.raw_value
            val_ix = chosen_ix.numeric_value

            if val_ix is None:
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="not_comparable",
                    company_facts_value=val_cf,
                    company_facts_concept=cf_fact.concept,
                    company_facts_unit=cf_fact.unit,
                    company_facts_period=cf_fact.period_end,
                    ixbrl_concept=chosen_ix.concept_name,
                    ixbrl_unit=chosen_ix.unit,
                    ixbrl_period=chosen_ix.end_date,
                    explanation="Inline XBRL fact value is non-numeric or unparseable.",
                ))
                continue

            diff = abs(val_cf - val_ix)
            if diff < 1e-4:  # Exact numeric match
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="exact_match",
                    company_facts_value=val_cf,
                    ixbrl_value=val_ix,
                    difference=0.0,
                    company_facts_concept=cf_fact.concept,
                    ixbrl_concept=chosen_ix.concept_name,
                    company_facts_unit=cf_fact.unit,
                    ixbrl_unit=chosen_ix.unit,
                    company_facts_period=cf_fact.period_end,
                    ixbrl_period=chosen_ix.end_date,
                    explanation=f"Exact match across Company Facts and Inline XBRL (${val_cf:,.0f}).",
                ))
            else:
                records.append(ReconciliationRecord(
                    accession_number=accession_number,
                    cik=cik,
                    metric_id=m.metric_id,
                    canonical_name=m.canonical_name,
                    status="value_mismatch",
                    company_facts_value=val_cf,
                    ixbrl_value=val_ix,
                    difference=diff,
                    company_facts_concept=cf_fact.concept,
                    ixbrl_concept=chosen_ix.concept_name,
                    company_facts_unit=cf_fact.unit,
                    ixbrl_unit=chosen_ix.unit,
                    company_facts_period=cf_fact.period_end,
                    ixbrl_period=chosen_ix.end_date,
                    explanation=f"Value discrepancy detected: Company Facts reported ${val_cf:,.0f} vs Inline XBRL reported ${val_ix:,.0f} (diff=${diff:,.0f}).",
                ))

        return records
