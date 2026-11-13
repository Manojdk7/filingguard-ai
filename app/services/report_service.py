"""
Report generation service for FilingGuard AI.
Generates comprehensive audit summaries, evidence dossiers, and verification reports.
"""
import datetime
from typing import Any, Dict, List, Optional

from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.fact_repository import FactRepository
from app.database.repositories.filing_repository import FilingRepository
from app.database.repositories.scoring_repository import ScoringRepository
from app.database.repositories.validation_repository import ValidationRepository


class AuditReportService:
    """Compiles structured audit reports across all pipeline stages."""

    def __init__(self):
        self.filing_repo = FilingRepository()
        self.fact_repo = FactRepository()
        self.scoring_repo = ScoringRepository()
        self.val_repo = ValidationRepository()
        self.audit_repo = AuditRepository()

    def generate_filing_audit_dossier(self, accession_number: str) -> Dict[str, Any]:
        """Compile a complete filing audit dossier with facts, scores, validations, and audit trail."""
        filing = self.filing_repo.get_by_accession(accession_number)
        facts = self.fact_repo.get_selected_facts_by_accession(accession_number)
        score = self.scoring_repo.get_filing_score(accession_number)
        validations = self.val_repo.get_validations_by_accession(accession_number)
        events = self.audit_repo.get_all_events(accession_number=accession_number)

        return {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "accession_number": accession_number,
            "company": filing.company_name if filing else "Unknown",
            "ticker": filing.ticker if filing else "N/A",
            "report_period": filing.report_period if filing else "N/A",
            "overall_score": score.overall_score if score else None,
            "overall_status": score.overall_status if score else "UNSCORED",
            "metrics_count": len(facts),
            "validations_summary": self.val_repo.get_validation_summary(accession_number),
            "audit_events_count": len(events),
        }

