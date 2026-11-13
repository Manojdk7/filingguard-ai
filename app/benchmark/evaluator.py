"""Reproducible evaluator for executable baselines and persisted FilingGuard facts."""
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.benchmark.metrics import (
    BenchmarkResult,
    compute_metrics,
    compute_per_company_breakdown,
    compute_per_metric_breakdown,
    values_match,
)
from app.benchmark.reference_loader import (
    ReferenceRecord,
    get_reference_summary,
    load_reference_dataset,
)
from app.database.repositories.benchmark_repository import (
    BenchmarkRepository,
    BenchmarkResultRecord,
)
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.fact_repository import FactRecord, FactRepository
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact, XBRLFactRepository
from app.extraction.taxonomy_mapping import TaxonomyMappingManager

logger = logging.getLogger("filingguard.benchmark.evaluator")


class BenchmarkEvaluator:
    """Orchestrates benchmark runs across baselines and the FilingGuard pipeline."""

    def __init__(
        self,
        fact_repo: Optional[FactRepository] = None,
        xbrl_repo: Optional[XBRLFactRepository] = None,
        bench_repo: Optional[BenchmarkRepository] = None,
        taxonomy_manager: Optional[TaxonomyMappingManager] = None,
        doc_repo: Optional[DocumentRepository] = None,
    ):
        self.fact_repo = fact_repo or FactRepository()
        self.xbrl_repo = xbrl_repo or XBRLFactRepository()
        self.bench_repo = bench_repo or BenchmarkRepository()
        self.taxonomy_manager = taxonomy_manager or TaxonomyMappingManager()
        self.doc_repo = doc_repo or DocumentRepository()
        self._document_hash_cache: Dict[str, tuple[Optional[str], str]] = {}

    def _verified_document_hash(self, accession_number: str, cik: str) -> tuple[Optional[str], str]:
        """Return the locally verified SEC document hash and the reason if unavailable."""
        if accession_number in self._document_hash_cache:
            return self._document_hash_cache[accession_number]

        doc = self.doc_repo.get_by_accession(accession_number)
        if not doc:
            result = (None, "No downloaded-document record exists for this accession.")
        elif doc.accession_number != accession_number or doc.cik.lstrip("0") != cik.lstrip("0"):
            result = (None, "Downloaded-document accession or CIK does not match the reference.")
        elif urlparse(doc.source_url or "").hostname not in {
            "www.sec.gov", "sec.gov", "archives.sec.gov", "data.sec.gov"
        }:
            result = (None, "Downloaded-document URL is not a recognized SEC host.")
        else:
            path = Path(doc.local_path)
            if not path.is_file():
                result = (None, "Downloaded filing document is not available locally.")
            else:
                try:
                    digest = hashlib.sha256()
                    with path.open("rb") as source:
                        for chunk in iter(lambda: source.read(65536), b""):
                            digest.update(chunk)
                except OSError as exc:
                    logger.warning("Unable to hash benchmark filing document for %s: %s", accession_number, exc)
                    result = (None, "Downloaded filing document could not be read for hashing.")
                else:
                    actual_hash = digest.hexdigest().lower()
                    if actual_hash != doc.sha256_hash.lower():
                        result = (None, "Downloaded filing document does not match its stored SHA-256.")
                    else:
                        result = (actual_hash, "")

        self._document_hash_cache[accession_number] = result
        return result

    def _has_traceable_evidence(
        self,
        ref: ReferenceRecord,
        fact: FactRecord,
        parsed_facts: List[ParsedXBRLFact],
    ) -> tuple[bool, str]:
        """Require a matching, locatable Inline XBRL fact tied to the verified filing bytes."""
        if (
            fact.accession_number != ref.accession_number
            or fact.cik.lstrip("0") != ref.cik.lstrip("0")
        ):
            return False, "Selected Company Facts accession or CIK does not match the reference."

        document_hash, failure_reason = self._verified_document_hash(
            ref.accession_number, ref.cik
        )
        if not document_hash:
            return False, failure_reason

        for parsed in parsed_facts:
            if (
                parsed.concept_name == fact.concept
                and parsed.numeric_value is not None
                and abs(parsed.numeric_value - fact.normalized_value) <= 1.0
                and (parsed.unit or "").upper() == (fact.unit or "").upper()
                and parsed.end_date == fact.period_end
                and parsed.period_type == fact.period_type
                and not parsed.is_segment
                and not parsed.dimensions
                and parsed.source_locator
                and (parsed.source_doc_hash or "").lower() == document_hash
            ):
                return True, f"Matched Inline XBRL source locator {parsed.source_locator} to the verified local filing hash."
        return False, "No Inline XBRL fact matched the selected concept, value, unit, period, locator, and filing hash."

    # -----------------------------------------------------------------------
    # Baseline A: Simple Tag Lookup
    # -----------------------------------------------------------------------

    def evaluate_simple_tag_baseline(
        self,
        records: List[ReferenceRecord],
    ) -> List[BenchmarkResult]:
        """Evaluate Baseline A: Simple tag lookup.

        Extracts facts by concept name lookup in raw parsed XBRL without
        advanced multi-year period resolution, dimensional filtering, or
        reconciliation. Naively selects the first parsed fact with a numeric value.
        """
        results: List[BenchmarkResult] = []

        # Cache parsed facts by accession
        facts_by_accession: Dict[str, list] = {}

        for ref in records:
            accn = ref.accession_number
            if accn not in facts_by_accession:
                facts_by_accession[accn] = self.xbrl_repo.get_facts_by_accession(accn)
            all_facts = facts_by_accession[accn]

            # Candidate concepts: reference expected concept + canonical taxonomy concepts
            m_def = self.taxonomy_manager.get_metric(ref.metric_id)
            candidate_concepts = set()
            if ref.expected_concept:
                candidate_concepts.add(ref.expected_concept)
            if m_def:
                candidate_concepts.update(m_def.concepts)

            # Naive lookup: find the first fact matching any candidate concept with a numeric value
            matched_fact = None
            for f in all_facts:
                if f.concept_name in candidate_concepts and f.numeric_value is not None:
                    matched_fact = f
                    break

            if matched_fact is not None:
                val = matched_fact.numeric_value
                unit = matched_fact.unit
                period = matched_fact.end_date
                concept = matched_fact.concept_name

                v_match = values_match(ref.expected_value, val)
                u_match = (unit or "").upper() == (ref.expected_unit or "").upper()
                p_match = period == ref.period_end
                c_match = concept == ref.expected_concept

                error = None
                if not v_match:
                    error = "value_mismatch"
                elif not p_match:
                    error = "period_mismatch"
                elif not u_match:
                    error = "unit_mismatch"

                results.append(
                    BenchmarkResult(
                        test_case_id=ref.test_case_id,
                        method="simple_tag",
                        metric_id=ref.metric_id,
                        accession_number=ref.accession_number,
                        company=ref.ticker,
                        expected_value=ref.expected_value,
                        expected_unit=ref.expected_unit,
                        expected_period=ref.period_end,
                        expected_concept=ref.expected_concept,
                        predicted_value=val,
                        predicted_unit=unit,
                        predicted_period=period,
                        predicted_concept=concept,
                        has_evidence=False,  # simple tag lookup does not trace evidence chains
                        is_value_match=v_match,
                        is_unit_match=u_match,
                        is_period_match=p_match,
                        is_concept_match=c_match,
                        error_type=error,
                        notes="Naive first-match concept lookup without period resolution",
                    )
                )
            else:
                results.append(
                    BenchmarkResult(
                        test_case_id=ref.test_case_id,
                        method="simple_tag",
                        metric_id=ref.metric_id,
                        accession_number=ref.accession_number,
                        company=ref.ticker,
                        expected_value=ref.expected_value,
                        expected_unit=ref.expected_unit,
                        expected_period=ref.period_end,
                        expected_concept=ref.expected_concept,
                        predicted_value=None,
                        predicted_unit=None,
                        predicted_period=None,
                        predicted_concept=None,
                        has_evidence=False,
                        is_value_match=False,
                        is_unit_match=False,
                        is_period_match=False,
                        is_concept_match=False,
                        error_type="missing",
                        notes="No matching concept fact found in raw parsed XBRL",
                    )
                )

        return results

    # -----------------------------------------------------------------------
    # Baseline B: LLM-Only Baseline
    # -----------------------------------------------------------------------

    def evaluate_llm_baseline(
        self,
        records: List[ReferenceRecord],
    ) -> List[BenchmarkResult]:
        """Return explicit not-evaluated rows until an LLM baseline is implemented."""
        return [
            BenchmarkResult(
                test_case_id=ref.test_case_id,
                method="llm_baseline",
                metric_id=ref.metric_id,
                accession_number=ref.accession_number,
                company=ref.ticker,
                expected_value=ref.expected_value,
                expected_unit=ref.expected_unit,
                expected_period=ref.period_end,
                expected_concept=ref.expected_concept,
                error_type="not_evaluated",
                notes="Not evaluated: no LLM baseline execution is implemented.",
            )
            for ref in records
        ]

    # -----------------------------------------------------------------------
    # Baseline C: Regex/Table extraction
    # -----------------------------------------------------------------------

    def evaluate_offline_regex_baseline(
        self,
        records: List[ReferenceRecord],
    ) -> List[BenchmarkResult]:
        """Mark the baseline unavailable until an independent extractor is implemented."""
        return [
            BenchmarkResult(
                test_case_id=ref.test_case_id,
                method="regex_simulation",
                metric_id=ref.metric_id,
                accession_number=ref.accession_number,
                company=ref.ticker,
                expected_value=ref.expected_value,
                expected_unit=ref.expected_unit,
                expected_period=ref.period_end,
                expected_concept=ref.expected_concept,
                error_type="not_evaluated",
                notes=(
                    "Not evaluated: the previous regex simulation derived predictions "
                    "from reference values and has been disabled."
                ),
            )
            for ref in records
        ]


    # -----------------------------------------------------------------------
    # Method D: FilingGuard Pipeline
    # -----------------------------------------------------------------------

    def evaluate_filingguard_pipeline(
        self,
        records: List[ReferenceRecord],
    ) -> List[BenchmarkResult]:
        """Evaluate Method C: FilingGuard hybrid pipeline.

        Uses the deterministic company facts extraction, semantic context selection,
        and cross-source evidence verification.
        """
        results: List[BenchmarkResult] = []

        # Cache selected facts and parsed Inline XBRL by accession
        facts_by_accession: Dict[str, list] = {}
        parsed_facts_by_accession: Dict[str, list] = {}

        for ref in records:
            accn = ref.accession_number
            if accn not in facts_by_accession:
                facts_by_accession[accn] = self.fact_repo.get_selected_facts_by_accession(accn)
                parsed_facts_by_accession[accn] = self.xbrl_repo.get_facts_by_accession(accn)
            selected_facts = facts_by_accession[accn]

            # Find selected fact matching the metric_id
            matched_fact = None
            for f in selected_facts:
                if (
                    f.metric_id == ref.metric_id
                    and f.accession_number == ref.accession_number
                    and f.cik.lstrip("0") == ref.cik.lstrip("0")
                ):
                    matched_fact = f
                    break

            if matched_fact is not None:
                val = matched_fact.normalized_value
                unit = matched_fact.unit
                period = matched_fact.period_end
                concept = matched_fact.concept

                v_match = values_match(ref.expected_value, val)
                u_match = (unit or "").upper() == (ref.expected_unit or "").upper()
                p_match = period == ref.period_end
                c_match = concept == ref.expected_concept

                error = None
                if not v_match:
                    error = "value_mismatch"
                elif not p_match:
                    error = "period_mismatch"
                elif not u_match:
                    error = "unit_mismatch"
                has_evidence, evidence_note = self._has_traceable_evidence(
                    ref, matched_fact, parsed_facts_by_accession[accn]
                )

                results.append(
                    BenchmarkResult(
                        test_case_id=ref.test_case_id,
                        method="filingguard",
                        metric_id=ref.metric_id,
                        accession_number=ref.accession_number,
                        company=ref.ticker,
                        expected_value=ref.expected_value,
                        expected_unit=ref.expected_unit,
                        expected_period=ref.period_end,
                        expected_concept=ref.expected_concept,
                        predicted_value=val,
                        predicted_unit=unit,
                        predicted_period=period,
                        predicted_concept=concept,
                        has_evidence=has_evidence,
                        is_value_match=v_match,
                        is_unit_match=u_match,
                        is_period_match=p_match,
                        is_concept_match=c_match,
                        error_type=error,
                        notes=f"Selected fact: {matched_fact.selection_explanation}. {evidence_note}",
                    )
                )
            else:
                results.append(
                    BenchmarkResult(
                        test_case_id=ref.test_case_id,
                        method="filingguard",
                        metric_id=ref.metric_id,
                        accession_number=ref.accession_number,
                        company=ref.ticker,
                        expected_value=ref.expected_value,
                        expected_unit=ref.expected_unit,
                        expected_period=ref.period_end,
                        expected_concept=ref.expected_concept,
                        predicted_value=None,
                        predicted_unit=None,
                        predicted_period=None,
                        predicted_concept=None,
                        has_evidence=False,
                        is_value_match=False,
                        is_unit_match=False,
                        is_period_match=False,
                        is_concept_match=False,
                        error_type="missing",
                        notes="Metric not present in selected company facts",
                    )
                )

        return results

    # -----------------------------------------------------------------------
    # Full Benchmark Orchestration
    # -----------------------------------------------------------------------

    def run_benchmark(
        self,
        records: Optional[List[ReferenceRecord]] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Run the full benchmark suite across all baselines and FilingGuard.

        Args:
            records: Optional custom list of reference records. If None,
                     loads from `data/reference/benchmark_reference.json`.
            persist: Whether to persist benchmark results to the database.

        Returns:
            Dict containing reference summary, method metrics, comparison table,
            and breakdowns.
        """
        ref_records = records or load_reference_dataset()
        summary = get_reference_summary(ref_records)
        anomaly_map = {r.test_case_id: r.has_anomaly for r in ref_records}

        logger.info("Executing benchmark across %d reference facts...", len(ref_records))

        # 1. Run Baseline A: Simple Tag
        results_simple = self.evaluate_simple_tag_baseline(ref_records)
        metrics_simple = compute_metrics(results_simple, anomaly_map)

        # 2. Run Baseline B: LLM
        results_llm = self.evaluate_llm_baseline(ref_records)
        metrics_llm = compute_metrics(results_llm, anomaly_map)

        # 3. Regex/table baseline is not evaluated until implemented independently.
        results_regex = self.evaluate_offline_regex_baseline(ref_records)
        metrics_regex = compute_metrics(results_regex, anomaly_map)

        # 4. Run Method D: FilingGuard
        results_fg = self.evaluate_filingguard_pipeline(ref_records)
        metrics_fg = compute_metrics(results_fg, anomaly_map)

        # Optional persistence
        if persist:
            self._persist_results(results_simple + results_llm + results_regex + results_fg)

        # Build comparison table
        comparison_table = self._build_comparison_table(
            ref_records, results_simple, results_llm, results_regex, results_fg
        )

        return {
            "reference_summary": summary,
            "metrics": {
                "simple_tag": metrics_simple.model_dump(),
                "llm_baseline": metrics_llm.model_dump(),
                "regex_simulation": metrics_regex.model_dump(),
                "filingguard": metrics_fg.model_dump(),
            },
            "detailed_results": {
                "simple_tag": [r.model_dump() for r in results_simple],
                "llm_baseline": [r.model_dump() for r in results_llm],
                "regex_simulation": [r.model_dump() for r in results_regex],
                "filingguard": [r.model_dump() for r in results_fg],
            },
            "comparison_table": comparison_table,
            "per_metric_breakdown": {
                "simple_tag": compute_per_metric_breakdown(results_simple),
                "regex_simulation": compute_per_metric_breakdown(results_regex),
                "filingguard": compute_per_metric_breakdown(results_fg),
            },
            "per_company_breakdown": {
                "simple_tag": compute_per_company_breakdown(results_simple),
                "regex_simulation": compute_per_company_breakdown(results_regex),
                "filingguard": compute_per_company_breakdown(results_fg),
            },
            "limitations": [
                f"The local reference set contains {len(ref_records)} records across {summary['company_count']} companies; its reviewer_verified flags are claims in the dataset, not independently audited by this evaluator.",
                "Reference records lack source URLs, exact fact contexts, and a documented independent verification method.",
                "LLM-only and regex/table baselines are not evaluated; no prediction values are synthesized for them.",
                "FilingGuard evidence support requires a value-, unit-, period-, and concept-matched Inline XBRL locator linked to the locally hash-verified filing.",
                "The FilingGuard benchmark reads locally persisted extraction results and is not a live SEC retrieval test.",
                "Non-standard fiscal calendars and issuer-specific disclosures may require context handling beyond this benchmark's current reference schema.",
            ],
        }

    def _persist_results(self, results: List[BenchmarkResult]) -> None:
        """Persist benchmark results to the database table."""
        self.bench_repo.clear_results()
        records_to_save: List[BenchmarkResultRecord] = []
        for r in results:
            if r.predicted_value is None:
                res_status = "SKIPPED" if r.error_type == "not_evaluated" else "MISSING"
            elif r.is_value_match and r.is_unit_match and r.is_period_match:
                res_status = "PASS"
            else:
                res_status = "FAIL"

            records_to_save.append(
                BenchmarkResultRecord(
                    benchmark_id=f"BM-{r.method}-{r.test_case_id}-{uuid.uuid4().hex[:6]}",
                    filing_id=r.accession_number,
                    test_case_id=r.test_case_id,
                    method=r.method,
                    metric_name=r.metric_id,
                    expected_value=r.expected_value,
                    expected_unit=r.expected_unit,
                    expected_period=r.expected_period,
                    predicted_value=r.predicted_value,
                    predicted_unit=r.predicted_unit,
                    predicted_period=r.predicted_period,
                    result=res_status,
                    reviewer_reference=r.test_case_id,
                    notes=r.notes,
                )
            )
        self.bench_repo.save_results(records_to_save)
        logger.info("Persisted %d benchmark result records to database", len(records_to_save))

    def _build_comparison_table(
        self,
        ref_records: List[ReferenceRecord],
        simple_res: List[BenchmarkResult],
        llm_res: List[BenchmarkResult],
        regex_res: List[BenchmarkResult],
        fg_res: List[BenchmarkResult],
    ) -> List[Dict[str, Any]]:
        """Build row-by-row comparison across all four methods."""
        simple_map = {r.test_case_id: r for r in simple_res}
        llm_map = {r.test_case_id: r for r in llm_res}
        regex_map = {r.test_case_id: r for r in regex_res}
        fg_map = {r.test_case_id: r for r in fg_res}

        rows: List[Dict[str, Any]] = []
        for ref in ref_records:
            cid = ref.test_case_id
            s = simple_map.get(cid)
            l = llm_map.get(cid)
            rx = regex_map.get(cid)
            f = fg_map.get(cid)

            rows.append({
                "test_case_id": cid,
                "company": ref.ticker,
                "metric_id": ref.metric_id,
                "expected_value": ref.expected_value,
                "simple_predicted": s.predicted_value if s else None,
                "simple_match": s.is_value_match if s else False,
                "llm_predicted": l.predicted_value if l else None,
                "llm_match": l.is_value_match if l else False,
                "regex_predicted": rx.predicted_value if rx else None,
                "regex_match": rx.is_value_match if rx else False,
                "fg_predicted": f.predicted_value if f else None,
                "fg_match": (
                    f.is_value_match and f.is_unit_match and f.is_period_match
                    if f
                    else False
                ),
                "evidence_support": f.has_evidence if f else False,
            })
        return rows
