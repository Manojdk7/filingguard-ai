import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("filingguard.scoring.escalation")

# Escalation and review routing categories
AUTO_PASS = "AUTO_PASS"
REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
MANDATORY_REVIEW = "MANDATORY_REVIEW"

# Score status categories
STATUS_HIGH = "HIGH"
STATUS_MEDIUM = "MEDIUM"
STATUS_LOW = "LOW"


class EscalationManager:
    """Evaluates mandatory review triggers and routing categories for metrics and filings."""

    def __init__(self, high_threshold: float = 0.85, medium_threshold: float = 0.60):
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold

    def determine_score_status(self, score: float) -> str:
        """Categorize a normalized score (0.0 to 1.0) into HIGH, MEDIUM, or LOW."""
        if score >= self.high_threshold:
            return STATUS_HIGH
        elif score >= self.medium_threshold:
            return STATUS_MEDIUM
        else:
            return STATUS_LOW

    def evaluate_metric_escalation(
        self,
        metric_id: str,
        canonical_name: str,
        score: float,
        is_missing: bool = False,
        is_ambiguous: bool = False,
        is_custom_extension: bool = False,
        custom_review_status: Optional[str] = None,
        is_segment_fact: bool = False,
        period_valid: bool = True,
        unit_valid: bool = True,
        reconciliation_status: Optional[str] = None,
        document_hash_matched: Optional[bool] = None,
        document_exists: Optional[bool] = None,
    ) -> Tuple[str, List[str], List[str]]:
        """Evaluate mandatory triggers and return (review_category, reduction_reasons, review_recommendations).

        In accordance with Section 8.2 of implementation.md:
        - Any wrong or ambiguous period/unit: mandatory review.
        - Any unresolved or candidate-for-review custom-tag mapping: mandatory review.
        - Any cross-source value mismatch: mandatory review.
        - Document integrity failure: mandatory review.
        - Low score (< 0.60): mandatory review.
        """
        reasons: List[str] = []
        recommendations: List[str] = []
        mandatory_triggers: List[str] = []

        # 1. Missing metric
        if is_missing:
            mandatory_triggers.append(f"Metric '{canonical_name}' is missing across evaluated SEC sources.")
            recommendations.append(
                f"Verify filing disclosures to determine if {canonical_name} is disclosed under alternative notes or single-step statements."
            )

        # 2. Document integrity triggers
        if document_exists is False:
            mandatory_triggers.append("Original primary filing document could not be located on disk.")
            recommendations.append("Re-download the original SEC filing and verify local storage permissions.")
        elif document_hash_matched is False:
            mandatory_triggers.append(
                "Document integrity verification failed: local file SHA-256 does not match recorded archive hash."
            )
            recommendations.append(
                "Investigate possible local file modification or corruption before relying on Inline XBRL evidence."
            )

        # 3. Period validity triggers
        if not period_valid:
            mandatory_triggers.append(
                f"Reporting period or context duration is invalid for {canonical_name}."
            )
            recommendations.append(
                "Inspect temporal context: ensure annual (~365 day) duration for flows or fiscal year-end instant for balances."
            )

        # 4. Unit validity triggers
        if not unit_valid:
            mandatory_triggers.append(f"Unit of measurement is invalid or unexpected for {canonical_name}.")
            recommendations.append("Inspect monetary unit tags: confirm ISO currency 'USD'.")

        # 5. Concept & Taxonomy triggers
        if is_segment_fact:
            mandatory_triggers.append(
                f"Dimensional/segment-level fact was excluded from consolidated {canonical_name}."
            )
            recommendations.append(
                "Verify whether an entity-wide consolidated disclosure exists or if only segmented breakdown was reported."
            )

        if is_custom_extension:
            if custom_review_status == "candidate_for_review":
                mandatory_triggers.append(
                    f"Mapped via company-specific custom extension tag flagged as 'candidate_for_review'."
                )
                recommendations.append(
                    f"Perform human auditor review to confirm custom extension semantic equivalence with {canonical_name}."
                )
            elif custom_review_status == "unresolved":
                mandatory_triggers.append(
                    f"Company custom extension tag could not be resolved to {canonical_name}."
                )
                recommendations.append("Audit custom taxonomy definition schema.")

        if is_ambiguous:
            mandatory_triggers.append(f"Multiple competing candidate facts detected for {canonical_name}.")
            recommendations.append("Manually disambiguate primary financial statement fact from footnote disclosures.")

        # 6. Reconciliation triggers
        if reconciliation_status == "value_mismatch":
            mandatory_triggers.append(
                "Cross-source value mismatch: SEC Company Facts and Inline XBRL report differing amounts."
            )
            recommendations.append(
                "Reconcile Path A and Path B: determine if differences stem from restatement, amended frames, or scaling."
            )
        elif reconciliation_status in ("period_mismatch", "unit_mismatch", "segment_vs_consolidated_mismatch"):
            mandatory_triggers.append(
                f"Cross-source divergence detected: reconciliation status is '{reconciliation_status}'."
            )
            recommendations.append("Inspect reconciliation difference breakdown.")

        # Combine reduction reasons
        reasons.extend(mandatory_triggers)

        # Determine routing category
        if mandatory_triggers or score < self.medium_threshold:
            category = MANDATORY_REVIEW
            if score < self.medium_threshold and not mandatory_triggers:
                reasons.append(
                    f"Confidence score ({score:.2f}) is below minimum threshold ({self.medium_threshold:.2f})."
                )
                recommendations.append("Full auditor review recommended due to composite low evidence quality.")
        elif score < self.high_threshold:
            category = REVIEW_RECOMMENDED
            reasons.append(
                f"Confidence score ({score:.2f}) is in intermediate range ({self.medium_threshold:.2f} - {self.high_threshold:.2f})."
            )
            recommendations.append("Secondary review recommended to verify single-source or minor variance items.")
        else:
            category = AUTO_PASS
            recommendations.append("Extraction satisfies high-confidence deterministic evidence criteria.")

        return category, reasons, recommendations

    def evaluate_filing_escalation(
        self,
        overall_score: float,
        assessed_count: int,
        missing_count: int,
        critical_metrics_present: bool,
        metric_categories: List[str],
        reduction_reasons: List[str],
    ) -> Tuple[str, str]:
        """Determine overall filing review category and summary explanation."""
        if any(cat == MANDATORY_REVIEW for cat in metric_categories):
            overall_category = MANDATORY_REVIEW
            summary = (
                f"Filing flagged for MANDATORY REVIEW: contains {metric_categories.count(MANDATORY_REVIEW)} "
                f"metric(s) with critical review triggers or low confidence."
            )
        elif not critical_metrics_present:
            overall_category = MANDATORY_REVIEW
            summary = (
                "Filing flagged for MANDATORY REVIEW: one or more core financial statement metrics "
                "(Revenue, Net Income, Assets, Liabilities, Equity) are missing."
            )
        elif overall_score < self.medium_threshold:
            overall_category = MANDATORY_REVIEW
            summary = f"Filing flagged for MANDATORY REVIEW: composite filing score ({overall_score:.2f}) is below {self.medium_threshold:.2f}."
        elif overall_score < self.high_threshold or any(cat == REVIEW_RECOMMENDED for cat in metric_categories):
            overall_category = REVIEW_RECOMMENDED
            summary = (
                f"Filing eligible for REVIEW RECOMMENDED: composite score {overall_score:.2f} with "
                f"{metric_categories.count(REVIEW_RECOMMENDED)} metric(s) flagged for secondary review."
            )
        else:
            overall_category = AUTO_PASS
            summary = (
                f"Filing eligible for AUTO PASS: composite score {overall_score:.2f} with all mandatory checks passing "
                "and zero escalation triggers."
            )

        return overall_category, summary

