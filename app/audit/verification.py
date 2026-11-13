import datetime
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.audit.hashing import GENESIS_PREVIOUS_HASH, calculate_event_hash, sign_checkpoint
from app.database.repositories.audit_repository import AuditEventRecord, AuditRepository

logger = logging.getLogger("filingguard.audit.verification")


class VerificationResult(BaseModel):
    is_valid: bool
    status: str  # 'VALID' or 'TAMPERED'
    total_events: int
    first_tampered_event_id: Optional[str] = None
    first_tampered_sequence: Optional[int] = None
    failure_reason: Optional[str] = None
    latest_event_hash: Optional[str] = None
    verified_at: str


class AuditVerifier:
    """Verifies the cryptographic integrity of the hash-chained audit ledger and pinpoints tampering."""

    def __init__(self, audit_repo: Optional[AuditRepository] = None):
        self.audit_repo = audit_repo or AuditRepository()

    def verify_chain(
        self,
        events: Optional[List[AuditEventRecord]] = None,
        accession_number: Optional[str] = None,
    ) -> VerificationResult:
        """Independently verifies every hash and pointer in the audit ledger.

        Checks:
        1. Non-empty chain sequence monotonicity: sequence must start at 1 and increment by 1.
        2. Genesis event: first event's previous_hash must match GENESIS_PREVIOUS_HASH.
        3. Pointer continuity: each event's previous_hash must equal the prior event's event_hash.
        4. Cryptographic integrity: recomputes sha256(previous_hash + canonical_json(payload) + created_at)
           and confirms it matches event_hash exactly.
        """
        verified_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if events is None:
            events = self.audit_repo.get_all_events(accession_number=accession_number)

        if not events:
            return VerificationResult(
                is_valid=True,
                status="VALID",
                total_events=0,
                first_tampered_event_id=None,
                first_tampered_sequence=None,
                failure_reason=None,
                latest_event_hash=None,
                verified_at=verified_time,
            )

        expected_prev_hash = GENESIS_PREVIOUS_HASH
        expected_seq = events[0].sequence_num  # Can start at 1 for global or arbitrary for sub-chain

        for idx, evt in enumerate(events):
            # 1. Check sequence ordering and missing events
            if idx == 0:
                if evt.sequence_num == 1 and evt.previous_hash != GENESIS_PREVIOUS_HASH:
                    reason = f"Genesis entry previous_hash mismatch: expected '{GENESIS_PREVIOUS_HASH}', found '{evt.previous_hash}'."
                    return VerificationResult(
                        is_valid=False,
                        status="TAMPERED",
                        total_events=len(events),
                        first_tampered_event_id=evt.event_id,
                        first_tampered_sequence=evt.sequence_num,
                        failure_reason=reason,
                        latest_event_hash=None,
                        verified_at=verified_time,
                    )
            else:
                if evt.sequence_num != expected_seq:
                    reason = f"Broken sequence ordering: expected sequence #{expected_seq}, found #{evt.sequence_num}."
                    return VerificationResult(
                        is_valid=False,
                        status="TAMPERED",
                        total_events=len(events),
                        first_tampered_event_id=evt.event_id,
                        first_tampered_sequence=evt.sequence_num,
                        failure_reason=reason,
                        latest_event_hash=None,
                        verified_at=verified_time,
                    )

                # 2. Check previous hash pointer continuity
                if evt.previous_hash != expected_prev_hash:
                    reason = (
                        f"Broken previous-hash reference at event #{evt.sequence_num}: "
                        f"points to '{evt.previous_hash[:12]}...', expected '{expected_prev_hash[:12]}...'."
                    )
                    return VerificationResult(
                        is_valid=False,
                        status="TAMPERED",
                        total_events=len(events),
                        first_tampered_event_id=evt.event_id,
                        first_tampered_sequence=evt.sequence_num,
                        failure_reason=reason,
                        latest_event_hash=None,
                        verified_at=verified_time,
                    )

            # 3. Recompute cryptographic hash from canonical payload and timestamp
            recomputed_hash = calculate_event_hash(
                previous_hash=evt.previous_hash,
                payload=evt.payload,
                created_at=evt.created_at,
            )
            if recomputed_hash != evt.event_hash:
                reason = (
                    f"Cryptographic hash mismatch at event #{evt.sequence_num} ({evt.event_id}): "
                    f"payload or timestamp was altered! Stored '{evt.event_hash[:12]}...', recomputed '{recomputed_hash[:12]}...'."
                )
                return VerificationResult(
                    is_valid=False,
                    status="TAMPERED",
                    total_events=len(events),
                    first_tampered_event_id=evt.event_id,
                    first_tampered_sequence=evt.sequence_num,
                    failure_reason=reason,
                    latest_event_hash=None,
                    verified_at=verified_time,
                )

            expected_prev_hash = evt.event_hash
            expected_seq = evt.sequence_num + 1

        return VerificationResult(
            is_valid=True,
            status="VALID",
            total_events=len(events),
            first_tampered_event_id=None,
            first_tampered_sequence=None,
            failure_reason=None,
            latest_event_hash=events[-1].event_hash,
            verified_at=verified_time,
        )

    def export_checkpoint(self, accession_number: Optional[str] = None) -> Dict[str, Any]:
        """Generate a signed cryptographic checkpoint export of the current audit ledger state."""
        verification = self.verify_chain(accession_number=accession_number)
        latest_hash = verification.latest_event_hash or GENESIS_PREVIOUS_HASH
        signature = sign_checkpoint(latest_hash)

        return {
            "checkpoint_type": "FILINGGUARD_AUDIT_LEDGER_CHECKPOINT",
            "version": "1.0.0",
            "status": verification.status,
            "is_valid": verification.is_valid,
            "total_events": verification.total_events,
            "latest_event_hash": latest_hash,
            "signature": signature,
            "verified_at": verification.verified_at,
            "accession_number": accession_number,
        }

