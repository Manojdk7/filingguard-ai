import hashlib
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.database.repositories.review_repository import ReviewRecord, ReviewRepository

logger = logging.getLogger("filingguard.review.idempotency")


def generate_idempotency_key(
    accession_number: str,
    metric_id: Optional[str],
    decision: str,
    reviewer_id: str,
    corrected_value: Optional[float] = None,
) -> str:
    """Generate a deterministic fallback idempotency key if none was supplied by client."""
    raw = f"{accession_number}:{metric_id or 'FILING'}:{decision.upper()}:{reviewer_id.strip()}:{corrected_value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def validate_idempotency_key(key: str) -> bool:
    """Validate that the idempotency key satisfies format constraints (non-empty, alphanumeric/dash/underscore)."""
    if not key or not isinstance(key, str):
        return False
    clean = key.strip()
    if len(clean) < 4 or len(clean) > 128:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_\-:]+$", clean))


class IdempotencyManager:
    """Manages review idempotency, detecting duplicate submissions and returning previous records."""

    def __init__(self, review_repo: Optional[ReviewRepository] = None):
        self.review_repo = review_repo or ReviewRepository()

    def check_idempotency(self, idempotency_key: str) -> Tuple[bool, Optional[ReviewRecord]]:
        """Check if an idempotency key has already been executed.
        
        Returns:
            (is_duplicate, existing_record)
        """
        if not idempotency_key:
            return False, None

        existing = self.review_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            logger.info(f"Duplicate submission detected for idempotency_key '{idempotency_key}'. Returning existing review {existing.review_id}.")
            return True, existing

        return False, None

