import datetime
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.audit.hashing import GENESIS_PREVIOUS_HASH, calculate_event_hash, sign_checkpoint
from app.database.repositories.audit_repository import AuditEventRecord, AuditRepository

logger = logging.getLogger("filingguard.audit.ledger")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AuditLedgerService:
    """Insert-only service managing cryptographic hash-chained audit events.

    Guarantees:
    - Every event links to the previous event's hash (forming a verifiable chain).
    - Initial event links to well-defined GENESIS_PREVIOUS_HASH.
    - Deterministic canonical JSON payload serialization.
    - Monotonically increasing sequence numbers.
    - Idempotent duplicate event suppression.
    - No modification or deletion capabilities.
    """

    def __init__(self, audit_repo: Optional[AuditRepository] = None):
        self.audit_repo = audit_repo or AuditRepository()

    def record_event(
        self,
        event_type: str,
        actor: str,
        payload: Dict[str, Any],
        accession_number: Optional[str] = None,
        workflow_id: Optional[str] = None,
        metric_id: Optional[str] = None,
        created_at: Optional[str] = None,
        prevent_duplicates: bool = True,
    ) -> AuditEventRecord:
        """Record an immutable, hash-chained audit event."""
        clean_actor = (actor or "").strip()
        if not clean_actor:
            raise ValueError("Actor identity is mandatory for audit events.")

        clean_type = (event_type or "").strip().upper()
        if not clean_type:
            raise ValueError("Event type is mandatory for audit events.")

        # Check for duplicate event if enabled
        if prevent_duplicates:
            dup = self.audit_repo.find_duplicate(
                event_type=clean_type,
                actor=clean_actor,
                accession_number=accession_number,
                metric_id=metric_id,
                payload=payload,
            )
            if dup:
                logger.info(f"Duplicate audit event suppressed for {clean_type} (existing evt #{dup.sequence_num}).")
                return dup

        # Resolve latest chain position
        latest = self.audit_repo.get_latest_event()
        if latest is None:
            sequence_num = 1
            previous_hash = GENESIS_PREVIOUS_HASH
        else:
            sequence_num = latest.sequence_num + 1
            previous_hash = latest.event_hash

        event_time = created_at or _now_iso()
        event_hash = calculate_event_hash(
            previous_hash=previous_hash,
            payload=payload,
            created_at=event_time,
        )
        event_id = f"evt_{sequence_num}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        signature = sign_checkpoint(event_hash)

        record = AuditEventRecord(
            event_id=event_id,
            sequence_num=sequence_num,
            workflow_id=workflow_id,
            accession_number=accession_number,
            metric_id=metric_id,
            event_type=clean_type,
            actor=clean_actor,
            payload=payload,
            previous_hash=previous_hash,
            event_hash=event_hash,
            created_at=event_time,
            signature=signature,
        )

        return self.audit_repo.append_event(record)

    def get_events(
        self,
        accession_number: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> List[AuditEventRecord]:
        """Query audit history in chronological order."""
        return self.audit_repo.get_all_events(
            accession_number=accession_number,
            workflow_id=workflow_id,
        )

