"""
Evidence locator formatting and citation utilities.
Extracts financial statement references and links facts to filing source lines.
"""
from typing import Dict, Optional


class EvidenceLocator:
    """Formats and extracts verifiable evidence references for financial facts."""

    @staticmethod
    def format_citation(
        statement_type: str,
        concept_name: str,
        page_or_line: Optional[str] = None,
        source_doc_hash: Optional[str] = None,
    ) -> str:
        """Construct a standardized citation string for auditor review."""
        stmt_label = statement_type.replace("_", " ").title()
        ref = f"{stmt_label} ({concept_name})"
        if page_or_line:
            ref += f" - {page_or_line}"
        if source_doc_hash:
            ref += f" [SHA256: {source_doc_hash[:8]}...]"
        return ref

    @staticmethod
    def parse_locator(locator_str: Optional[str]) -> Dict[str, Optional[str]]:
        """Parse an XBRL source locator string into component parts."""
        if not locator_str:
            return {"statement": None, "line": None, "page": None}

        parts = locator_str.split(",")
        return {
            "statement": parts[0].strip() if len(parts) > 0 else None,
            "line": parts[1].strip() if len(parts) > 1 else None,
            "page": parts[2].strip() if len(parts) > 2 else None,
        }

