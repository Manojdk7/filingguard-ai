from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    event_id: str
    sequence_num: int
    workflow_id: Optional[str] = None
    accession_number: Optional[str] = None
    metric_id: Optional[str] = None
    event_type: str
    actor: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    previous_hash: str
    event_hash: str
    created_at: str
    signature: Optional[str] = None


class VerificationResponse(BaseModel):
    is_valid: bool
    status: str  # 'VALID' or 'TAMPERED'
    total_events: int
    first_tampered_event_id: Optional[str] = None
    first_tampered_sequence: Optional[int] = None
    failure_reason: Optional[str] = None
    latest_event_hash: Optional[str] = None
    verified_at: str


class CheckpointExportResponse(BaseModel):
    checkpoint_type: str = "FILINGGUARD_AUDIT_LEDGER_CHECKPOINT"
    version: str = "1.0.0"
    status: str
    is_valid: bool
    total_events: int
    latest_event_hash: str
    signature: str
    verified_at: str
    accession_number: Optional[str] = None

