"""Load typed benchmark reference records and summarize their provenance fields."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger("filingguard.benchmark.reference_loader")

DEFAULT_REFERENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "benchmark_reference.json"


class ReferenceRecord(BaseModel):
    """A benchmark reference fact with separately reported verification claims."""
    test_case_id: str
    company_name: str
    ticker: str
    cik: str
    accession_number: str
    fiscal_year: int
    period_end: str
    period_type: str
    metric_id: str
    canonical_name: str
    expected_value: float
    expected_unit: str
    expected_concept: str
    statement_type: str
    evidence_source: str
    reviewer_verified: bool
    has_anomaly: bool
    source_url: Optional[str] = None
    filing_form: Optional[str] = None
    filing_date: Optional[str] = None
    context_id: Optional[str] = None
    evidence_locator: Optional[str] = None
    verification_method: Optional[str] = None


def load_reference_dataset(path: Optional[Path] = None) -> List[ReferenceRecord]:
    """Load and validate the benchmark reference dataset from JSON.
    
    Args:
        path: Path to the reference JSON file.  Falls back to the default
              location ``data/reference/benchmark_reference.json``.
    
    Returns:
        List of validated ReferenceRecord objects.
    
    Raises:
        FileNotFoundError: If the dataset file does not exist.
        ValueError: If the dataset is empty or contains invalid records.
    """
    file_path = path or DEFAULT_REFERENCE_PATH
    if not file_path.exists():
        raise FileNotFoundError(f"Reference dataset not found at {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("Reference dataset must be a non-empty JSON array")

    records: List[ReferenceRecord] = []
    seen_ids: set = set()
    for idx, item in enumerate(data):
        rec = ReferenceRecord(**item)
        if not rec.reviewer_verified:
            logger.warning(
                "Reference record %s (%s) has reviewer_verified=false – "
                "results for this record may not be authoritative.",
                rec.test_case_id, rec.metric_id,
            )
        if rec.test_case_id in seen_ids:
            raise ValueError(f"Duplicate test_case_id: {rec.test_case_id}")
        seen_ids.add(rec.test_case_id)
        records.append(rec)

    logger.info("Loaded %d reference records from %s", len(records), file_path)
    return records


def group_by_accession(records: List[ReferenceRecord]) -> Dict[str, List[ReferenceRecord]]:
    """Group reference records by accession number."""
    groups: Dict[str, List[ReferenceRecord]] = {}
    for rec in records:
        groups.setdefault(rec.accession_number, []).append(rec)
    return groups


def get_reference_summary(records: List[ReferenceRecord]) -> Dict:
    """Return a summary of the reference dataset for reporting."""
    companies = set()
    accessions = set()
    metrics_covered = set()
    anomaly_count = 0
    for rec in records:
        companies.add(rec.ticker)
        accessions.add(rec.accession_number)
        metrics_covered.add(rec.metric_id)
        if rec.has_anomaly:
            anomaly_count += 1

    return {
        "total_reference_facts": len(records),
        "companies": sorted(companies),
        "company_count": len(companies),
        "filing_count": len(accessions),
        "accession_numbers": sorted(accessions),
        "metrics_covered": sorted(metrics_covered),
        "metric_coverage_count": len(metrics_covered),
        "anomaly_count": anomaly_count,
        "all_reviewer_verified": all(r.reviewer_verified for r in records),
        "reviewer_verified_count": sum(r.reviewer_verified for r in records),
        "reviewer_verification_status": (
            "not_independently_audited"
            if any(r.reviewer_verified for r in records)
            else "no_reviewer_verification_claims"
        ),
        "source_url_count": sum(bool(r.source_url) for r in records),
        "evidence_locator_count": sum(bool(r.evidence_locator) for r in records),
        "verification_method_count": sum(bool(r.verification_method) for r in records),
        "independent_review_method_documented": all(bool(r.verification_method) for r in records),
    }
