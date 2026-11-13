import hashlib
import json
import logging
import os
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from app.config import settings
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.fact_repository import FactRecord, FactRepository
from app.database.repositories.filing_repository import FilingRecord, FilingRepository
from app.database.repositories.reconciliation_repository import (
    ReconciliationRecord,
    ReconciliationRepository,
)
from app.database.repositories.scoring_repository import (
    FilingConfidenceRecord,
    MetricConfidenceRecord,
    ScoringRepository,
)
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact, XBRLFactRepository
from app.extraction.taxonomy_mapping import MetricDefinition, TaxonomyMappingManager
from app.scoring.escalation import (
    AUTO_PASS,
    MANDATORY_REVIEW,
    REVIEW_RECOMMENDED,
    STATUS_HIGH,
    STATUS_LOW,
    STATUS_MEDIUM,
    EscalationManager,
)

logger = logging.getLogger("filingguard.scoring.quality_score")


class DocumentIntegrityResult(BaseModel):
    exists: bool
    hash_matched: bool
    calculated_hash: Optional[str] = None
    stored_hash: Optional[str] = None
    local_path: Optional[str] = None
    source_url: Optional[str] = None
    accession_number: Optional[str] = None
    cik: Optional[str] = None
    file_size_bytes: Optional[int] = None
    notes: str


class ConfidenceScoringEngine:
    """Deterministic evidence and confidence scoring engine for SEC 10-K financial disclosures."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        scoring_repo: Optional[ScoringRepository] = None,
        fact_repo: Optional[FactRepository] = None,
        recon_repo: Optional[ReconciliationRepository] = None,
        doc_repo: Optional[DocumentRepository] = None,
        xbrl_repo: Optional[XBRLFactRepository] = None,
        filing_repo: Optional[FilingRepository] = None,
        taxonomy_manager: Optional[TaxonomyMappingManager] = None,
    ):
        self.config_path = config_path or (settings.CONFIG_DIR / "scoring_config.json")
        self.config = self._load_config()

        self.scoring_repo = scoring_repo or ScoringRepository()
        self.fact_repo = fact_repo or FactRepository()
        self.recon_repo = recon_repo or ReconciliationRepository()
        self.doc_repo = doc_repo or DocumentRepository()
        self.xbrl_repo = xbrl_repo or XBRLFactRepository()
        self.filing_repo = filing_repo or FilingRepository()
        self.taxonomy_manager = taxonomy_manager or TaxonomyMappingManager()

        self.weights = self.config.get("weights", {
            "source_reliability": 0.30,
            "cross_source_agreement": 0.15,
            "period_compatibility": 0.20,
            "unit_dimensional_compatibility": 0.10,
            "extraction_mapping_quality": 0.25,
        })
        self.thresholds = self.config.get("thresholds", {
            "high_confidence_min": 0.85,
            "medium_confidence_min": 0.60,
        })
        self.critical_metrics = self.config.get("critical_metrics", [
            "revenue", "net_income", "total_assets", "total_liabilities", "stockholders_equity"
        ])
        self.escalation = EscalationManager(
            high_threshold=self.thresholds.get("high_confidence_min", 0.85),
            medium_threshold=self.thresholds.get("medium_confidence_min", 0.60),
        )

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load scoring config from {self.config_path}: {e}")
        return {
            "version": "2.0.0",
            "weights": {
                "source_reliability": 0.30,
                "cross_source_agreement": 0.15,
                "period_compatibility": 0.20,
                "unit_dimensional_compatibility": 0.10,
                "extraction_mapping_quality": 0.25,
            },
            "thresholds": {
                "high_confidence_min": 0.85,
                "medium_confidence_min": 0.60,
            },
            "critical_metrics": [
                "revenue", "net_income", "total_assets", "total_liabilities", "stockholders_equity"
            ],
        }

    def verify_document_integrity(self, accession_number: str) -> DocumentIntegrityResult:
        """Verify downloaded original primary document existence and SHA-256 cryptographic hash."""
        doc = self.doc_repo.get_by_accession(accession_number)
        if not doc:
            return DocumentIntegrityResult(
                exists=False,
                hash_matched=False,
                accession_number=accession_number,
                notes="No original document record found in database for accession.",
            )

        if not os.path.exists(doc.local_path):
            return DocumentIntegrityResult(
                exists=False,
                hash_matched=False,
                stored_hash=doc.sha256_hash,
                local_path=doc.local_path,
                source_url=doc.source_url,
                accession_number=doc.accession_number,
                cik=doc.cik,
                notes=f"Document file not found at expected local path: {doc.local_path}",
            )

        try:
            hasher = hashlib.sha256()
            with open(doc.local_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            calculated_hash = hasher.hexdigest().lower()
            stored_hash = doc.sha256_hash.lower()

            matched = calculated_hash == stored_hash
            notes = (
                "Document integrity verified: local file SHA-256 matches recorded archive hash. "
                "(Note: Matching local hash proves consistency with the retrieved copy, "
                "not independent authenticity of the SEC source)."
                if matched
                else f"Integrity failure: calculated hash {calculated_hash} does not match stored hash {stored_hash}."
            )

            return DocumentIntegrityResult(
                exists=True,
                hash_matched=matched,
                calculated_hash=calculated_hash,
                stored_hash=stored_hash,
                local_path=doc.local_path,
                source_url=doc.source_url,
                accession_number=doc.accession_number,
                cik=doc.cik,
                file_size_bytes=doc.file_size_bytes,
                notes=notes,
            )
        except Exception as e:
            logger.error(f"Error computing document hash for {doc.local_path}: {e}")
            return DocumentIntegrityResult(
                exists=True,
                hash_matched=False,
                stored_hash=doc.sha256_hash,
                local_path=doc.local_path,
                source_url=doc.source_url,
                accession_number=doc.accession_number,
                cik=doc.cik,
                notes=f"Failed to read or hash document file: {e}",
            )

    def calculate_metric_confidence(
        self,
        metric: MetricDefinition,
        accession_number: str,
        cik: str,
        target_report_period: Optional[str],
        company_fact: Optional[FactRecord],
        recon_record: Optional[ReconciliationRecord],
        custom_candidates: List[Any],
        integrity_result: DocumentIntegrityResult,
    ) -> MetricConfidenceRecord:
        """Calculate an evidence-based five-factor quality score for one metric."""
        metric_id = metric.metric_id
        canonical_name = metric.canonical_name
        is_missing = company_fact is None and (recon_record is None or recon_record.status == "missing_in_both")
        is_ambiguous = company_fact is not None and company_fact.status == "ambiguous"
        is_segment_fact = recon_record is not None and recon_record.is_segment_mismatch
        concept_used = company_fact.concept if company_fact else (recon_record.ixbrl_concept if recon_record else None)
        taxonomy_used = company_fact.taxonomy if company_fact else None
        is_custom_extension = False
        custom_review_status = None
        if concept_used:
            is_standard = taxonomy_used in ("us-gaap", "dei") and not taxonomy_used.startswith("http")
            if not is_standard and concept_used not in metric.concepts:
                custom_review = next(
                    (c for c in custom_candidates if getattr(c, "custom_concept", None) == concept_used),
                    None,
                )
                if not custom_review:
                    custom_review = next(
                        (c for c in custom_candidates if getattr(c, "candidate_metric_id", None) == metric_id),
                        None,
                    )
                is_custom_extension = True
                custom_review_status = custom_review.confidence_level if custom_review else "unresolved"

        positive_factors: List[str] = []
        negative_factors: List[str] = []
        recon_status = recon_record.status if recon_record else ("missing_in_both" if is_missing else None)
        factor_evidence: Dict[str, Dict[str, Any]] = {}

        def record_factor(
            name: str,
            score: float,
            evidence: List[str],
            deductions: List[str],
        ) -> float:
            score = round(max(0.0, min(1.0, score)), 4)
            weight = self.weights[name]
            factor_evidence[name] = {
                "raw_score": score,
                "weight": weight,
                "weighted_contribution": round(score * weight, 4),
                "evidence": evidence,
                "deduction_reasons": deductions,
            }
            positive_factors.extend(evidence)
            negative_factors.extend(deductions)
            return score

        fact_identity_matches = bool(
            company_fact
            and company_fact.accession_number == accession_number
            and company_fact.cik.lstrip("0") == cik.lstrip("0")
        )
        document_identity_matches = bool(
            integrity_result.accession_number == accession_number
            and integrity_result.cik
            and integrity_result.cik.lstrip("0") == cik.lstrip("0")
        )
        source_host = urlparse(integrity_result.source_url or "").hostname
        source_is_sec = source_host in {"www.sec.gov", "sec.gov", "archives.sec.gov", "data.sec.gov"}
        source_evidence: List[str] = []
        source_deductions: List[str] = []
        if is_missing:
            source_score = 0.0
            source_deductions.append("Metric absent: no selected fact or usable source value is available.")
        elif integrity_result.exists and not integrity_result.hash_matched:
            source_score = 0.0
            source_deductions.append("Stored filing document failed its SHA-256 consistency check.")
        elif not fact_identity_matches and company_fact:
            source_score = 0.0
            source_deductions.append("Company Facts accession or CIK does not match the requested filing.")
        elif integrity_result.hash_matched and document_identity_matches and source_is_sec:
            source_score = 0.85
            source_evidence.extend([
                "Company Facts identity matches the requested accession and CIK."
                if fact_identity_matches
                else "An Inline XBRL source value is recorded for the requested filing.",
                "Stored document matches its recorded SHA-256 and has a SEC-hosted source URL.",
            ])
            source_deductions.append(
                "Local hash consistency does not independently authenticate the retrieved bytes against SEC."
            )
        elif fact_identity_matches or (recon_record and recon_record.ixbrl_value is not None):
            source_score = 0.55
            source_evidence.append("A source value is tied to the requested filing accession.")
            if not integrity_result.exists:
                source_deductions.append("Original filing document is not available for local integrity verification.")
            else:
                source_deductions.append("Document source URL or filing identity could not be fully verified.")
        else:
            source_score = 0.0
            source_deductions.append("Source identity could not be verified from the available records.")
        source_score = record_factor(
            "source_reliability", source_score, source_evidence, source_deductions
        )

        cross_evidence: List[str] = []
        cross_deductions: List[str] = []
        if recon_status == "exact_match":
            cross_score = 1.0
            cross_evidence.append("Company Facts and Inline XBRL selected values reconcile exactly.")
        elif recon_status == "value_mismatch":
            cross_score = 0.15
            cross_deductions.append(
                f"Value mismatch: cross-source values differ by {recon_record.difference}; "
                "reviewer reconciliation is required."
            )
        elif recon_status in ("missing_in_ixbrl", "missing_in_company_facts"):
            cross_score = 0.45
            cross_deductions.append(
                f"Cross-source check is incomplete: {recon_status.replace('_', ' ')}."
            )
        elif recon_status in ("period_mismatch", "unit_mismatch"):
            cross_score = 0.10
            cross_deductions.append(f"Cross-source {recon_status.replace('_', ' ')} requires review.")
        elif recon_status == "segment_vs_consolidated_mismatch":
            cross_score = 0.0
            cross_deductions.append("Only a dimensional segment fact was available for a consolidated metric.")
        elif recon_status == "missing_in_both":
            cross_score = 0.0
            cross_deductions.append("Neither source contains a usable value for this metric.")
        elif recon_record and recon_record.ixbrl_value is not None:
            cross_score = 0.25
            cross_deductions.append("The stored reconciliation does not establish an exact cross-source match.")
        else:
            cross_score = 0.0
            cross_deductions.append("No cross-source reconciliation evidence is available.")
        cross_score = record_factor(
            "cross_source_agreement", cross_score, cross_evidence, cross_deductions
        )

        period_evidence: List[str] = []
        period_deductions: List[str] = []
        period_valid = False
        period_score = 0.0
        if company_fact and company_fact.period_type != metric.period_type:
            period_deductions.append(
                f"Expected {metric.period_type} context, received {company_fact.period_type}."
            )
        elif company_fact and target_report_period and company_fact.period_end:
            try:
                target_date = datetime.strptime(target_report_period[:10], "%Y-%m-%d")
                end_date = datetime.strptime(company_fact.period_end[:10], "%Y-%m-%d")
                end_delta = abs((target_date - end_date).days)
                if end_delta > 7:
                    period_deductions.append(
                        f"Fact end date {company_fact.period_end} differs from filing period "
                        f"{target_report_period} by {end_delta} days."
                    )
                elif metric.period_type == "instant":
                    period_score = 1.0
                    period_valid = True
                    period_evidence.append(f"Instant fact date matches filing period within {end_delta} days.")
                elif not company_fact.period_start:
                    period_deductions.append("Duration fact has no start date; annual compatibility is unverified.")
                else:
                    start_date = datetime.strptime(company_fact.period_start[:10], "%Y-%m-%d")
                    duration_days = (end_date - start_date).days
                    if 350 <= duration_days <= 375:
                        period_score = 1.0
                        period_valid = True
                        period_evidence.append(f"Duration is {duration_days} days and aligns with the filing end date.")
                    elif 120 <= duration_days <= 420:
                        period_score = 0.5
                        period_deductions.append(
                            f"Duration is {duration_days} days, outside the expected annual range (350-375)."
                        )
                    else:
                        if duration_days < 120:
                            period_deductions.append(
                                f"Quarterly period ({duration_days} days) cannot substitute for an annual metric."
                            )
                        else:
                            period_deductions.append(
                                f"Duration of {duration_days} days is incompatible with an annual financial metric."
                            )
            except (TypeError, ValueError):
                period_deductions.append("Period dates are missing or invalid; compatibility cannot be established.")
        elif recon_record and recon_record.ixbrl_period and target_report_period:
            try:
                ixbrl_end = datetime.strptime(recon_record.ixbrl_period[:10], "%Y-%m-%d")
                target_date = datetime.strptime(target_report_period[:10], "%Y-%m-%d")
                if abs((ixbrl_end - target_date).days) <= 7:
                    period_score = 0.5
                    period_evidence.append("Inline XBRL end date aligns, but full period context is unavailable.")
                    period_deductions.append("Duration start date or complete period context is not recorded.")
                else:
                    period_deductions.append("Inline XBRL end date does not align with the filing period.")
            except (TypeError, ValueError):
                period_deductions.append("Inline XBRL period is not a parseable date.")
        else:
            period_deductions.append("Required fact period or filing report period is unavailable.")
        period_score = record_factor(
            "period_compatibility", period_score, period_evidence, period_deductions
        )

        unit_used = company_fact.unit if company_fact else (recon_record.ixbrl_unit if recon_record else None)
        unit_evidence: List[str] = []
        unit_deductions: List[str] = []
        unit_valid = bool(unit_used and unit_used.upper() == metric.default_unit.upper())
        if is_segment_fact:
            unit_score = 0.0
            unit_valid = False
            unit_deductions.append("Dimensional segment evidence cannot establish entity-wide compatibility.")
        elif not unit_used:
            unit_score = 0.0
            unit_valid = False
            unit_deductions.append("No fact unit is available.")
        elif not unit_valid or (
            recon_record
            and recon_record.ixbrl_unit
            and recon_record.ixbrl_unit.upper() != metric.default_unit.upper()
        ):
            unit_score = 0.0
            unit_valid = False
            unit_deductions.append(
                f"Expected unit {metric.default_unit}; observed Company Facts/Inline XBRL unit "
                f"{unit_used}/{recon_record.ixbrl_unit if recon_record else 'not available'}."
            )
        elif recon_status == "exact_match":
            unit_score = 1.0
            unit_evidence.append(
                f"Expected unit {metric.default_unit} agrees across both entity-wide source facts."
            )
        elif recon_status == "value_mismatch":
            unit_score = 0.8
            unit_evidence.append(f"Units agree with expected {metric.default_unit} in both source facts.")
            unit_deductions.append("Cross-source dimensional context is present, but the values disagree.")
        else:
            unit_score = 0.5
            unit_evidence.append(f"Observed unit matches expected {metric.default_unit}.")
            unit_deductions.append("Entity-wide dimensional compatibility is not corroborated by both sources.")
        unit_score = record_factor(
            "unit_dimensional_compatibility", unit_score, unit_evidence, unit_deductions
        )

        mapping_evidence: List[str] = []
        mapping_deductions: List[str] = []
        if is_missing or is_segment_fact:
            mapping_score = 0.0
            mapping_deductions.append(
                "No usable entity-wide fact is available for the canonical metric."
                if is_missing
                else "Dimensional segment-level fact excluded from consolidated metric mapping."
            )
        elif is_ambiguous:
            mapping_score = 0.3
            mapping_deductions.append("Multiple competing candidate facts exist for this canonical metric.")
        elif is_custom_extension:
            mapping_score = 0.5 if custom_review_status == "candidate_for_review" else 0.1
            mapping_deductions.append(
                f"Company extension mapping is {custom_review_status}; semantic equivalence is not established."
            )
        elif company_fact and company_fact.status != "selected":
            mapping_score = 0.4
            mapping_deductions.append(
                f"Fact status is '{company_fact.status}', not selected for extraction."
            )
        elif concept_used in metric.concepts:
            concept_index = metric.concepts.index(concept_used)
            namespace_verified = taxonomy_used in ("us-gaap", "dei")
            mapping_score = (
                (1.0 if concept_index == 0 else 0.9)
                if namespace_verified
                else (0.75 if concept_index == 0 else 0.65)
            )
            mapping_evidence.append(
                f"Mapped to {'primary' if concept_index == 0 else 'approved alternative'} concept {concept_used}."
            )
            if not namespace_verified:
                mapping_deductions.append("Taxonomy namespace is not available to verify this concept mapping.")
        elif concept_used and taxonomy_used in ("us-gaap", "dei"):
            mapping_score = 0.7
            mapping_evidence.append(f"Mapped to standard taxonomy concept {concept_used}.")
            mapping_deductions.append("Concept is not in the configured canonical concept list.")
        elif concept_used:
            mapping_score = 0.4
            mapping_deductions.append("Inline XBRL concept is recorded but its taxonomy mapping is not verified.")
        else:
            mapping_score = 0.0
            mapping_deductions.append("No concept or mapping evidence is available.")
        mapping_score = record_factor(
            "extraction_mapping_quality", mapping_score, mapping_evidence, mapping_deductions
        )

        factors = {
            "source_reliability": source_score,
            "cross_source_agreement": cross_score,
            "period_compatibility": period_score,
            "unit_dimensional_compatibility": unit_score,
            "extraction_mapping_quality": mapping_score,
        }
        raw_score = sum(factor_evidence[key]["weighted_contribution"] for key in self.weights)
        confidence_score = round(max(0.0, min(1.0, raw_score)), 4)
        quality_score_100 = round(confidence_score * 100.0, 2)

        review_cat, reduction_reasons, recommendations = self.escalation.evaluate_metric_escalation(
            metric_id=metric_id,
            canonical_name=canonical_name,
            score=confidence_score,
            is_missing=is_missing,
            is_ambiguous=is_ambiguous,
            is_custom_extension=is_custom_extension,
            custom_review_status=custom_review_status,
            is_segment_fact=is_segment_fact,
            period_valid=period_valid,
            unit_valid=unit_valid,
            reconciliation_status=recon_status,
            document_hash_matched=integrity_result.hash_matched if integrity_result.exists else None,
            document_exists=integrity_result.exists,
        )
        status = self.escalation.determine_score_status(confidence_score)
        evidence_references = {
            "accession_number": accession_number,
            "cik": cik,
            "metric_id": metric_id,
            "canonical_name": canonical_name,
            "company_facts_concept": company_fact.concept if company_fact else None,
            "ixbrl_concept": recon_record.ixbrl_concept if recon_record else None,
            "primary_document": integrity_result.local_path,
            "document_sha256": integrity_result.stored_hash,
            "document_source_url": integrity_result.source_url,
            "integrity_notes": integrity_result.notes,
            "factor_breakdown": factor_evidence,
        }
        explanation = (
            f"Metric '{canonical_name}' scored {confidence_score:.4f} ({quality_score_100:.1f}/100) "
            f"under scoring rubric {self.config.get('version', '2.0.0')} "
            f"({status}; {review_cat}). "
        )
        if positive_factors:
            explanation += f"Strengths: {'; '.join(positive_factors)}. "
        if negative_factors:
            explanation += f"Deficiencies: {'; '.join(negative_factors)}. "

        return MetricConfidenceRecord(
            accession_number=accession_number,
            cik=cik,
            metric_id=metric_id,
            canonical_name=canonical_name,
            confidence_score=confidence_score,
            quality_score_100=quality_score_100,
            status=status,
            review_category=review_cat,
            factors=factors,
            positive_factors=positive_factors,
            negative_factors=negative_factors,
            evidence_references=evidence_references,
            explanation=explanation.strip(),
            review_recommendations=recommendations,
            version=self.config.get("version", "2.0.0"),
        )

    def calculate_filing_confidence(
        self,
        accession_number: str,
        cik: str,
        metric_scores: List[MetricConfidenceRecord],
    ) -> FilingConfidenceRecord:
        """Aggregate metric-level confidence into transparent overall filing score."""
        all_metrics = self.taxonomy_manager.get_all_metrics()
        total_metrics_count = len(all_metrics)

        scored_by_id = {s.metric_id: s for s in metric_scores}
        assessed_count = len([s for s in metric_scores if s.confidence_score > 0.0])
        missing_count = total_metrics_count - assessed_count

        # Check critical core metrics
        missing_critical = [m for m in self.critical_metrics if m not in scored_by_id or scored_by_id[m].confidence_score == 0.0]
        critical_present = len(missing_critical) == 0

        # Composite score: unweighted average of canonical metrics
        metric_scores_list = [s.confidence_score for s in metric_scores]
        composite_score = sum(metric_scores_list) / len(metric_scores_list) if metric_scores_list else 0.0

        # Incomplete filing penalty: if critical metrics are missing, score is penalized and capped
        reduction_reasons: List[str] = []
        if not critical_present:
            composite_score = min(composite_score, 0.70)
            reduction_reasons.append(
                f"Filing assessment is INCOMPLETE: missing critical core metrics ({', '.join(missing_critical)})."
            )

        if missing_count > 0 and critical_present:
            reduction_reasons.append(
                f"Filing disclosure omission: {missing_count} of {total_metrics_count} canonical metrics missing."
            )

        # Collect metrics that reduce score
        for s in metric_scores:
            if s.confidence_score < self.thresholds.get("high_confidence_min", 0.85):
                reduction_reasons.append(f"Metric '{s.canonical_name}' scored {s.confidence_score:.2f} ({s.review_category}).")

        overall_score = round(max(0.0, min(1.0, composite_score)), 4)
        quality_score_100 = round(overall_score * 100.0, 2)

        # Filing status and escalation
        metric_cats = [s.review_category for s in metric_scores]
        overall_category, summary_explanation = self.escalation.evaluate_filing_escalation(
            overall_score=overall_score,
            assessed_count=assessed_count,
            missing_count=missing_count,
            critical_metrics_present=critical_present,
            metric_categories=metric_cats,
            reduction_reasons=reduction_reasons,
        )
        overall_status = self.escalation.determine_score_status(overall_score)

        score_factors = {
            "mean_metric_confidence": round(sum(metric_scores_list) / len(metric_scores_list), 4) if metric_scores_list else 0.0,
            "assessed_metrics_ratio": round(assessed_count / total_metrics_count, 4) if total_metrics_count else 0.0,
            "critical_metrics_ratio": round((len(self.critical_metrics) - len(missing_critical)) / len(self.critical_metrics), 4),
        }

        return FilingConfidenceRecord(
            accession_number=accession_number,
            cik=cik,
            overall_score=overall_score,
            quality_score_100=quality_score_100,
            overall_status=overall_status,
            overall_review_category=overall_category,
            metrics_assessed_count=assessed_count,
            metrics_missing_count=missing_count,
            critical_metrics_present=critical_present,
            score_factors=score_factors,
            reduction_reasons=reduction_reasons,
            summary_explanation=summary_explanation,
            version=self.config.get("version", "2.0.0"),
        )

    def score_filing(self, accession_number: str) -> Tuple[FilingConfidenceRecord, List[MetricConfidenceRecord]]:
        """Execute full evidence and confidence evaluation for a filing accession and persist results."""
        filing = self.filing_repo.get_by_accession(accession_number)
        cik = filing.cik if filing else "0000000000"
        target_report_period = filing.report_period if filing else None

        # Verify document integrity
        integrity_result = self.verify_document_integrity(accession_number)

        # Fetch underlying data
        all_canonical_metrics = self.taxonomy_manager.get_all_metrics()
        facts = self.fact_repo.get_selected_facts_by_accession(accession_number)
        facts_by_metric = {f.metric_id: f for f in facts}

        reconciliations = self.recon_repo.get_reconciliations_by_accession(accession_number)
        recons_by_metric = {r.metric_id: r for r in reconciliations}

        custom_candidates = self.recon_repo.get_custom_candidates_by_accession(accession_number)

        # Score each canonical metric
        metric_scores: List[MetricConfidenceRecord] = []
        for metric in all_canonical_metrics:
            m_id = metric.metric_id
            m_score = self.calculate_metric_confidence(
                metric=metric,
                accession_number=accession_number,
                cik=cik,
                target_report_period=target_report_period,
                company_fact=facts_by_metric.get(m_id),
                recon_record=recons_by_metric.get(m_id),
                custom_candidates=custom_candidates,
                integrity_result=integrity_result,
            )
            metric_scores.append(m_score)

        # Calculate overall filing confidence
        filing_score = self.calculate_filing_confidence(
            accession_number=accession_number,
            cik=cik,
            metric_scores=metric_scores,
        )

        # Persist results
        self.scoring_repo.save_metric_scores(metric_scores)
        self.scoring_repo.save_filing_score(filing_score)

        logger.info(
            f"Filing {accession_number} scored: overall {filing_score.overall_score:.4f} "
            f"({filing_score.overall_status}) - Category: {filing_score.overall_review_category}"
        )

        return filing_score, metric_scores
