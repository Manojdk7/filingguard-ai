import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas.audit import (
    AuditEventResponse,
    CheckpointExportResponse,
    VerificationResponse,
)
from app.audit.ledger import AuditLedgerService
from app.audit.verification import AuditVerifier

logger = logging.getLogger("filingguard.api.audit")

router = APIRouter(prefix="/audit", tags=["Tamper-Evident Audit Ledger"])


@router.get(
    "/events",
    response_model=List[AuditEventResponse],
    status_code=status.HTTP_200_OK,
    summary="Get chronological audit ledger events",
)
def get_audit_events_endpoint(
    accession_number: Optional[str] = Query(None, description="Optional filter by filing accession number"),
    workflow_id: Optional[str] = Query(None, description="Optional filter by workflow thread ID"),
) -> List[AuditEventResponse]:
    """Retrieve immutable, hash-chained audit events in sequential order."""
    try:
        service = AuditLedgerService()
        events = service.get_events(
            accession_number=accession_number.strip() if accession_number else None,
            workflow_id=workflow_id.strip() if workflow_id else None,
        )
        return [
            AuditEventResponse(
                event_id=e.event_id,
                sequence_num=e.sequence_num,
                workflow_id=e.workflow_id,
                accession_number=e.accession_number,
                metric_id=e.metric_id,
                event_type=e.event_type,
                actor=e.actor,
                payload=e.payload,
                previous_hash=e.previous_hash,
                event_hash=e.event_hash,
                created_at=e.created_at,
                signature=e.signature,
            )
            for e in events
        ]
    except Exception as e:
        logger.error(f"Error retrieving audit events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query audit events: {str(e)}",
        )


@router.get(
    "/verify",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Cryptographically verify audit ledger hash chain",
)
def verify_audit_ledger_endpoint(
    accession_number: Optional[str] = Query(None, description="Optional filter to verify chain for specific filing"),
) -> VerificationResponse:
    """Independently recalculate all hashes and verify pointer continuity across the ledger.

    Returns:
    - VALID: If all hashes and previous_hash pointers match perfectly.
    - TAMPERED: If any payload, hash, timestamp, or pointer was altered, identifying the exact failure.
    """
    try:
        verifier = AuditVerifier()
        result = verifier.verify_chain(
            accession_number=accession_number.strip() if accession_number else None
        )
        return VerificationResponse(
            is_valid=result.is_valid,
            status=result.status,
            total_events=result.total_events,
            first_tampered_event_id=result.first_tampered_event_id,
            first_tampered_sequence=result.first_tampered_sequence,
            failure_reason=result.failure_reason,
            latest_event_hash=result.latest_event_hash,
            verified_at=result.verified_at,
        )
    except Exception as e:
        logger.error(f"Error during audit chain verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failure: {str(e)}",
        )


@router.get(
    "/export",
    response_model=CheckpointExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Export signed cryptographic audit ledger checkpoint",
)
def export_checkpoint_endpoint(
    accession_number: Optional[str] = Query(None, description="Optional filter for filing checkpoint"),
) -> CheckpointExportResponse:
    """Generate a signed cryptographic checkpoint summarizing the audit ledger state."""
    try:
        verifier = AuditVerifier()
        export_data = verifier.export_checkpoint(
            accession_number=accession_number.strip() if accession_number else None
        )
        return CheckpointExportResponse(**export_data)
    except Exception as e:
        logger.error(f"Error exporting checkpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Checkpoint export failure: {str(e)}",
        )

