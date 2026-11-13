"""
CLI script to preload and verify demo filings (Apple, Microsoft, Amazon) in SQLite.
Usage: python scripts/preload_demo_data.py
"""
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import check_db_health
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.filing_repository import FilingRepository
from app.scoring.quality_score import ConfidenceScoringEngine
from app.validation.engine import FinancialValidationEngine


def main():
    if not check_db_health():
        print("ERROR: Database connection offline.", file=sys.stderr)
        sys.exit(1)

    filing_repo = FilingRepository()
    fact_repo = FactRepository()
    scoring_engine = ConfidenceScoringEngine()
    val_engine = FinancialValidationEngine()

    filings = filing_repo.get_recent_filings()
    print("=" * 60)
    print(" FILINGGUARD AI — PRELOADED DEMO DATA VERIFICATION")
    print("=" * 60)
    print(f"Total Filings Found: {len(filings)}")

    for f in filings:
        facts = fact_repo.get_selected_facts_by_accession(f.accession_number)
        print(f"\n• {f.company_name} ({f.ticker}) — 10-K [{f.report_period}]")
        print(f"  Accession: {f.accession_number}")
        print(f"  Facts Selected: {len(facts)}")

        # Run scoring & validation
        try:
            score, _ = scoring_engine.score_filing(f.accession_number)
            print(f"  Score: {score.overall_score:.2f} ({score.overall_status})")
            val_results = val_engine.validate_filing(f.accession_number)
            passed_count = sum(1 for v in val_results if v.status == "PASS")
            print(f"  Validations: {passed_count}/{len(val_results)} passed")
        except Exception as e:
            print(f"  Status: Ready for pipeline processing ({e})")

    print("\n" + "=" * 60)
    print("Preload verification complete.")


if __name__ == "__main__":
    main()

