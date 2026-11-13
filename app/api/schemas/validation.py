from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ValidationResultResponse(BaseModel):
    id: Optional[int] = None
    accession_number: str
    cik: str
    rule_id: str
    rule_name: str
    rule_version: str = "1.0.0"
    validation_category: str
    status: str = Field(..., description="PASS, FAIL, WARNING, or NOT_EVALUATED")
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    absolute_difference: Optional[float] = None
    relative_difference: Optional[float] = None
    configured_tolerance: Optional[float] = None
    input_metrics: Dict[str, Any]
    evidence_references: Dict[str, Any]
    explanation: str
    failure_reason: Optional[str] = None
    recommendation: Optional[str] = None
    created_at: Optional[str] = None


class ValidationSummaryResponse(BaseModel):
    accession_number: str
    total_rules: int
    passed: int
    failed: int
    warnings: int
    not_evaluated: int
    validations: Optional[List[ValidationResultResponse]] = None

